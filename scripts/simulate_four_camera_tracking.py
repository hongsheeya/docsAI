#!/usr/bin/env python3
"""Run a synthetic four-corner camera tracking/performance simulation.

This does not claim real multi-camera accuracy. It creates four deterministic
corner-like views from the same sample video, adds camera-specific occlusion,
runs YOLO pose, and measures whether camera fusion recovers single-view blind
spots within the current CPU/runtime envelope.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import time
from pathlib import Path

import cv2
import numpy as np


PROJECT = Path('/opt/app/project/main')
DEFAULT_VIDEO = PROJECT / 'src' / 'assets' / 'pres' / 'sample-fall.mp4'
DEFAULT_MODEL = Path('/opt/app/yolov8n-pose.pt')
OUT_DIR = PROJECT / 'outputs' / 'performance'

CAMERAS = [
    {
        'id': 'corner_nw',
        'label': '좌상단 코너',
        'tilt': (-0.08, -0.06),
        'shift': (-0.05, -0.03),
        'brightness': 1.06,
        'contrast': 1.04,
        'occluder': 'right_band',
    },
    {
        'id': 'corner_ne',
        'label': '우상단 코너',
        'tilt': (0.08, -0.05),
        'shift': (0.05, -0.02),
        'brightness': 0.98,
        'contrast': 1.08,
        'occluder': 'left_band',
    },
    {
        'id': 'corner_sw',
        'label': '좌하단 코너',
        'tilt': (-0.07, 0.07),
        'shift': (-0.04, 0.04),
        'brightness': 1.00,
        'contrast': 0.96,
        'occluder': 'top_band',
    },
    {
        'id': 'corner_se',
        'label': '우하단 코너',
        'tilt': (0.07, 0.07),
        'shift': (0.04, 0.04),
        'brightness': 0.94,
        'contrast': 1.02,
        'occluder': 'moving_panel',
    },
]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return float(values[0])
    pos = (len(values) - 1) * pct
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(values[lo])
    return float(values[lo] + (values[hi] - values[lo]) * (pos - lo))


def read_frames(video_path: Path, max_frames: int, stride: int) -> tuple[list[np.ndarray], dict]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f'cannot open video: {video_path}')
    meta = {
        'source_fps': float(cap.get(cv2.CAP_PROP_FPS) or 0),
        'source_frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
        'source_width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
        'source_height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
    }
    frames: list[np.ndarray] = []
    idx = 0
    while len(frames) < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % max(1, stride) == 0:
            frames.append(frame)
        idx += 1
    cap.release()
    if not frames:
        raise RuntimeError(f'no frames read from video: {video_path}')
    return frames, meta


def apply_corner_view(frame: np.ndarray, camera: dict, frame_idx: int, canvas_w: int, canvas_h: int) -> np.ndarray:
    base = cv2.resize(frame, (canvas_w, canvas_h), interpolation=cv2.INTER_AREA)
    h, w = base.shape[:2]
    tx, ty = camera['tilt']
    sx, sy = camera['shift']
    src = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
    dst = np.float32([
        [w * (0.03 + sx), h * (0.03 + sy)],
        [w * (0.97 + tx + sx), h * (0.04 + sy)],
        [w * (0.96 + sx), h * (0.96 + ty + sy)],
        [w * (0.04 + tx + sx), h * (0.97 + sy)],
    ])
    warped = cv2.warpPerspective(base, cv2.getPerspectiveTransform(src, dst), (w, h), borderMode=cv2.BORDER_REPLICATE)
    warped = cv2.convertScaleAbs(warped, alpha=float(camera['contrast']), beta=int((float(camera['brightness']) - 1.0) * 45))
    return add_occlusion(warped, str(camera['occluder']), frame_idx)


def add_occlusion(frame: np.ndarray, mode: str, frame_idx: int) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]
    color = (18, 18, 18)
    alpha = 0.84
    overlay = out.copy()
    phase = (frame_idx % 12) / 11.0
    if mode == 'right_band':
        x1 = int(w * (0.66 + 0.05 * math.sin(frame_idx * 0.5)))
        cv2.rectangle(overlay, (x1, int(h * 0.12)), (w, int(h * 0.94)), color, -1)
    elif mode == 'left_band':
        x2 = int(w * (0.32 + 0.05 * math.cos(frame_idx * 0.4)))
        cv2.rectangle(overlay, (0, int(h * 0.08)), (x2, int(h * 0.9)), color, -1)
    elif mode == 'top_band':
        y2 = int(h * (0.26 + 0.05 * math.sin(frame_idx * 0.35)))
        cv2.rectangle(overlay, (int(w * 0.08), 0), (int(w * 0.92), y2), color, -1)
    elif mode == 'moving_panel':
        x1 = int(w * (0.22 + phase * 0.42))
        x2 = min(w, x1 + int(w * 0.2))
        cv2.rectangle(overlay, (x1, int(h * 0.16)), (x2, int(h * 0.92)), color, -1)
    return cv2.addWeighted(overlay, alpha, out, 1.0 - alpha, 0)


def build_views(frames: list[np.ndarray], canvas_w: int, canvas_h: int) -> tuple[list[np.ndarray], list[dict]]:
    views: list[np.ndarray] = []
    index: list[dict] = []
    for frame_idx, frame in enumerate(frames):
        for camera in CAMERAS:
            views.append(apply_corner_view(frame, camera, frame_idx, canvas_w, canvas_h))
            index.append({
                'frame_idx': frame_idx,
                'camera_id': camera['id'],
                'camera_label': camera['label'],
            })
    return views, index


def detection_summary(result, quality_threshold: float) -> dict:
    boxes = getattr(result, 'boxes', None)
    keypoints = getattr(result, 'keypoints', None)
    if boxes is None or len(boxes) == 0:
        return {
            'detected': False,
            'quality': 0.0,
            'box_conf': 0.0,
            'visible_keypoints': 0,
            'mean_keypoint_conf': 0.0,
        }
    conf_arr = boxes.conf.detach().cpu().numpy() if getattr(boxes, 'conf', None) is not None else np.zeros((len(boxes),))
    best_idx = int(np.argmax(conf_arr)) if len(conf_arr) else 0
    box_conf = float(conf_arr[best_idx]) if len(conf_arr) else 0.0
    visible = 0
    mean_kp_conf = 0.0
    if keypoints is not None and getattr(keypoints, 'data', None) is not None:
        kp = keypoints.data.detach().cpu().numpy()
        if kp.ndim >= 3 and best_idx < kp.shape[0] and kp.shape[2] >= 3:
            kp_conf = kp[best_idx, :, 2]
            visible = int(np.sum(kp_conf >= 0.25))
            mean_kp_conf = float(np.mean(kp_conf)) if kp_conf.size else 0.0
    quality = box_conf * (0.45 + 0.55 * min(1.0, visible / 17.0)) * (0.55 + 0.45 * min(1.0, mean_kp_conf))
    return {
        'detected': bool(quality >= quality_threshold and visible >= 5),
        'quality': round(float(quality), 4),
        'box_conf': round(box_conf, 4),
        'visible_keypoints': int(visible),
        'mean_keypoint_conf': round(mean_kp_conf, 4),
    }


def run_pose(model_path: Path, views: list[np.ndarray], imgsz: int, conf: float, repeats: int):
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    model.predict(source=[views[0]], imgsz=imgsz, conf=conf, verbose=False, device='cpu')
    elapsed_runs: list[float] = []
    result_runs = []
    for _ in range(max(1, repeats)):
        started = time.perf_counter()
        results = model.predict(source=views, imgsz=imgsz, conf=conf, verbose=False, device='cpu')
        elapsed_runs.append(time.perf_counter() - started)
        result_runs.append(results)
    median_idx = sorted(range(len(elapsed_runs)), key=lambda idx: elapsed_runs[idx])[len(elapsed_runs) // 2]
    return result_runs[median_idx], elapsed_runs


def analyze(index: list[dict], results, quality_threshold: float, frame_count: int) -> dict:
    per_view = []
    for meta, result in zip(index, results):
        item = {**meta, **detection_summary(result, quality_threshold)}
        per_view.append(item)
    by_camera = {}
    for camera in CAMERAS:
        rows = [item for item in per_view if item['camera_id'] == camera['id']]
        detected = [item for item in rows if item['detected']]
        by_camera[camera['id']] = {
            'label': camera['label'],
            'frames': len(rows),
            'detected_frames': len(detected),
            'recall': round(len(detected) / max(1, len(rows)), 4),
            'mean_quality': round(statistics.mean([item['quality'] for item in rows]), 4) if rows else 0.0,
            'mean_visible_keypoints': round(statistics.mean([item['visible_keypoints'] for item in rows]), 2) if rows else 0.0,
        }
    fused_frames = []
    primary_recovered = 0
    primary_id = CAMERAS[0]['id']
    for frame_idx in range(frame_count):
        rows = [item for item in per_view if item['frame_idx'] == frame_idx]
        detected = [item for item in rows if item['detected']]
        best = max(rows, key=lambda item: item['quality']) if rows else {}
        primary_ok = any(item['camera_id'] == primary_id and item['detected'] for item in rows)
        fused_ok = bool(detected)
        if fused_ok and not primary_ok:
            primary_recovered += 1
        fused_frames.append({
            'frame_idx': frame_idx,
            'fused_detected': fused_ok,
            'detected_camera_count': len(detected),
            'best_camera_id': best.get('camera_id'),
            'best_quality': best.get('quality', 0.0),
            'best_visible_keypoints': best.get('visible_keypoints', 0),
        })
    fused_detected = [item for item in fused_frames if item['fused_detected']]
    detected_counts = [item['detected_camera_count'] for item in fused_frames]
    multi_view_frames = [item for item in fused_frames if item['detected_camera_count'] >= 2]
    single_view_only = [item for item in fused_frames if item['detected_camera_count'] == 1]
    return {
        'per_camera': by_camera,
        'fused': {
            'frames': frame_count,
            'detected_frames': len(fused_detected),
            'target_recall': round(len(fused_detected) / max(1, frame_count), 4),
            'multi_view_supported_frames': len(multi_view_frames),
            'single_view_only_frames': len(single_view_only),
            'mean_detected_camera_count': round(statistics.mean(detected_counts), 2) if detected_counts else 0.0,
            'primary_blindspot_recovered_frames': primary_recovered,
            'primary_blindspot_recovery_rate': round(primary_recovered / max(1, frame_count), 4),
            'mean_best_quality': round(statistics.mean([item['best_quality'] for item in fused_frames]), 4) if fused_frames else 0.0,
            'mean_best_visible_keypoints': round(statistics.mean([item['best_visible_keypoints'] for item in fused_frames]), 2) if fused_frames else 0.0,
        },
        'sample_frames': fused_frames[:12],
    }


def save_montage(views: list[np.ndarray], output_path: Path, canvas_w: int, canvas_h: int) -> None:
    first = views[:4]
    labelled = []
    for frame, camera in zip(first, CAMERAS):
        image = frame.copy()
        cv2.putText(image, camera['label'], (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(image, camera['label'], (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (40, 160, 255), 1, cv2.LINE_AA)
        labelled.append(cv2.resize(image, (canvas_w // 2, canvas_h // 2), interpolation=cv2.INTER_AREA))
    top = np.concatenate([labelled[0], labelled[1]], axis=1)
    bottom = np.concatenate([labelled[2], labelled[3]], axis=1)
    montage = np.concatenate([top, bottom], axis=0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), montage)


def write_report(payload: dict, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    perf = payload['performance']
    fused = payload['tracking']['fused']
    lines = [
        '# 4카메라 코너 시뮬레이션 성능 테스트',
        '',
        f"- 갱신: `{payload['updated_at']}`",
        f"- 입력 영상: `{payload['input']['video']}`",
        f"- pose model: `{payload['input']['model']}`",
        f"- 조건: 4 camera x {payload['input']['frames_per_camera']} frames, imgsz {payload['input']['imgsz']}, conf {payload['input']['conf']}",
        f"- 주의: `{payload['limitations'][0]}`",
        '',
        '## 결론',
        '',
        payload['conclusion'],
        '',
        '## RTT/처리량',
        '',
        '| 항목 | 값 |',
        '| --- | ---: |',
        f"| 전체 처리 view | {perf['total_views']} |",
        f"| 전체 pose FPS | {perf['pose_view_fps']} |",
        f"| 카메라별 등가 FPS | {perf['equivalent_fps_per_camera']} |",
        f"| 4초 청크 추정 RTT p50 | {perf['estimated_4s_chunk_rtt_p50_sec']}s |",
        f"| 4초 청크 추정 RTT p95 | {perf['estimated_4s_chunk_rtt_p95_sec']}s |",
        f"| 4fps x 4대 실시간 여유율 | {perf['realtime_headroom_ratio']}x |",
        '',
        '## 추적/가림 복구',
        '',
        '| 항목 | 값 |',
        '| --- | ---: |',
        f"| 4카메라 fused target recall | {fused['target_recall'] * 100:.1f}% |",
        f"| 평균 동시 검출 카메라 수 | {fused['mean_detected_camera_count']}대 |",
        f"| 2대 이상 근거 확보 프레임 | {fused['multi_view_supported_frames']} / {fused['frames']} |",
        f"| 단일 카메라만 보인 프레임 | {fused['single_view_only_frames']} / {fused['frames']} |",
        f"| primary blind spot 복구 | {fused['primary_blindspot_recovered_frames']} / {fused['frames']} |",
        f"| best view 평균 keypoint | {fused['mean_best_visible_keypoints']}개 |",
        '',
        '## 카메라별 결과',
        '',
        '| 카메라 | recall | 평균 quality | 평균 visible KP |',
        '| --- | ---: | ---: | ---: |',
    ]
    for camera_id, row in payload['tracking']['per_camera'].items():
        lines.append(
            f"| {row['label']} `{camera_id}` | {row['recall'] * 100:.1f}% | "
            f"{row['mean_quality']:.4f} | {row['mean_visible_keypoints']:.2f} |"
        )
    lines.extend([
        '',
        '## 운영 판단',
        '',
    ])
    lines.extend(f'- {item}' for item in payload['operational_judgement'])
    lines.extend([
        '',
        '## 한계',
        '',
    ])
    lines.extend(f'- {item}' for item in payload['limitations'])
    if payload.get('artifacts', {}).get('montage'):
        lines.extend(['', '## 시뮬레이션 뷰 샘플', '', f"![4 camera montage]({payload['artifacts']['montage']})"])
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', default=str(DEFAULT_VIDEO))
    parser.add_argument('--model', default=str(DEFAULT_MODEL))
    parser.add_argument('--frames', type=int, default=32)
    parser.add_argument('--stride', type=int, default=4)
    parser.add_argument('--imgsz', type=int, default=320)
    parser.add_argument('--conf', type=float, default=0.15)
    parser.add_argument('--quality-threshold', type=float, default=0.18)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--canvas-w', type=int, default=640)
    parser.add_argument('--canvas-h', type=int, default=480)
    parser.add_argument('--tag', default='')
    args = parser.parse_args()

    frames, video_meta = read_frames(Path(args.video), max(1, args.frames), max(1, args.stride))
    views, index = build_views(frames, max(320, args.canvas_w), max(240, args.canvas_h))
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')
    tag = args.tag or f'{args.imgsz}'
    base = OUT_DIR / f'four_camera_sim_{stamp}_{tag}'
    montage_path = base.with_suffix('.montage.jpg')
    save_montage(views, montage_path, max(320, args.canvas_w), max(240, args.canvas_h))

    results, elapsed_runs = run_pose(Path(args.model), views, int(args.imgsz), float(args.conf), max(1, args.repeats))
    tracking = analyze(index, results, float(args.quality_threshold), len(frames))

    total_views = len(views)
    median_elapsed = percentile(elapsed_runs, 0.5)
    pose_fps = total_views / max(median_elapsed, 1e-9)
    chunk_views = 4 * 4 * 4
    chunk_rtts = [elapsed * chunk_views / max(total_views, 1) for elapsed in elapsed_runs]
    realtime_required_fps = 4 * 4
    headroom = pose_fps / max(realtime_required_fps, 1e-9)
    fused_recall = tracking['fused']['target_recall']
    p95_rtt = percentile(chunk_rtts, 0.95)
    if fused_recall >= 0.95 and p95_rtt <= 4.0:
        verdict = 'prototype_pass'
        conclusion = '합성 4코너 시뮬레이션에서는 4초 청크 안에 처리되고, 단일 카메라 가림을 다른 코너 뷰가 상당 부분 복구했습니다. 실제 운영 전에는 실제 4카메라 동시 촬영 검증이 필요합니다.'
    elif p95_rtt <= 4.0:
        verdict = 'throughput_pass_tracking_needs_tuning'
        conclusion = '처리량은 4초 청크 기준 통과했지만, 합성 가림 조건의 fused recall이 목표치보다 낮아 카메라 배치/ROI/품질 필터 튜닝이 필요합니다.'
    else:
        verdict = 'throughput_risk'
        conclusion = '4카메라 pose 처리량이 4초 청크 기준으로 빠듯합니다. 해상도, 샘플링 fps, ROI 분리 또는 추론 장치 조정이 필요합니다.'

    payload = {
        'updated_at': now(),
        'verdict': verdict,
        'conclusion': conclusion,
        'input': {
            'video': str(Path(args.video)),
            'model': str(Path(args.model)),
            'frames_per_camera': len(frames),
            'total_views': total_views,
            'stride': int(args.stride),
            'imgsz': int(args.imgsz),
            'conf': float(args.conf),
            'quality_threshold': float(args.quality_threshold),
            'repeats': max(1, args.repeats),
            **video_meta,
        },
        'performance': {
            'elapsed_runs_sec': [round(float(v), 4) for v in elapsed_runs],
            'median_elapsed_sec': round(float(median_elapsed), 4),
            'total_views': total_views,
            'pose_view_fps': round(float(pose_fps), 2),
            'equivalent_fps_per_camera': round(float(pose_fps / 4.0), 2),
            'estimated_4s_chunk_views': chunk_views,
            'estimated_4s_chunk_rtt_p50_sec': round(float(percentile(chunk_rtts, 0.5)), 3),
            'estimated_4s_chunk_rtt_p95_sec': round(float(p95_rtt), 3),
            'realtime_required_pose_fps': realtime_required_fps,
            'realtime_headroom_ratio': round(float(headroom), 2),
        },
        'tracking': tracking,
        'operational_judgement': [
            '한 대상 기준 4개 코너 카메라 융합은 처리량 면에서 가능성이 있습니다.',
            '단일 카메라만으로는 occluder 방향에 따라 끊김이 생기므로 global person_id 융합이 필요합니다.',
            '운영에서는 best view를 고르는 기준을 box confidence보다 keypoint visibility 중심으로 둬야 합니다.',
            '낙상/행동 알림은 카메라별 OR가 아니라 동일 global person의 시간 근접 evidence로 병합해야 합니다.',
            '실제 검증 합격 기준은 target recall 95% 이상, p95 RTT 4초 이하, ID switch가 이벤트 판단을 깨지 않는 수준으로 잡는 것이 맞습니다.',
        ],
        'limitations': [
            '실제 4대 카메라 촬영이 아니라 단일 영상을 원근/가림 변환한 synthetic simulation입니다.',
            '실제 방 모서리 시점의 렌즈 왜곡, 사람 회전, 조명 차이, 카메라 간 시간 오차는 완전히 반영하지 못합니다.',
            '이번 수치는 pose 추론과 synthetic fusion 중심이며, 실제 행동/낙상 분류 정확도는 4카메라 라벨셋으로 별도 측정해야 합니다.',
            '현재 장비의 CPU 부하와 백그라운드 학습 상태에 따라 RTT는 달라질 수 있습니다.',
        ],
        'artifacts': {
            'montage': str(montage_path),
        },
    }
    json_path = base.with_suffix('.json')
    md_path = base.with_suffix('.md')
    write_report(payload, json_path, md_path)
    print(json.dumps({'ok': True, 'json': str(json_path), 'md': str(md_path), 'verdict': verdict, 'summary': payload['performance'], 'tracking': tracking['fused']}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
