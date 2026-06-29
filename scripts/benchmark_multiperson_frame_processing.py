#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import math
import os
import statistics
import time
from pathlib import Path

import cv2
import numpy as np


PROJECT = Path('/opt/app/project/main')
DEFAULT_VIDEO = PROJECT / 'src' / 'assets' / 'pres' / 'sample-fall.mp4'
DEFAULT_MODEL = Path('/opt/app/yolov8n-pose.pt')
OUT_DIR = PROJECT / 'outputs' / 'performance'


def now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def read_frames(video_path, max_frames, stride):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f'cannot open video: {video_path}')
    frames = []
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
    return frames


def synthesize_people(frame, count, canvas_w=1280, canvas_h=720):
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    cols = min(count, max(1, int(math.ceil(math.sqrt(count * (canvas_w / max(canvas_h, 1)))))))
    rows = int(math.ceil(count / cols))
    cell_w = canvas_w // cols
    cell_h = canvas_h // rows
    src_h, src_w = frame.shape[:2]
    scale = min(cell_w / max(1, src_w), cell_h / max(1, src_h)) * 0.92
    target_w = max(1, int(src_w * scale))
    target_h = max(1, int(src_h * scale))
    resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
    for i in range(count):
        row = i // cols
        col = i % cols
        x = col * cell_w + max(0, (cell_w - target_w) // 2)
        y = row * cell_h + max(0, (cell_h - target_h) // 2)
        x2 = min(canvas_w, x + target_w)
        y2 = min(canvas_h, y + target_h)
        canvas[y:y2, x:x2] = resized[: y2 - y, : x2 - x]
    return canvas


def summarize_result(result):
    boxes = result.boxes
    kpts = getattr(result, 'keypoints', None)
    det_count = 0 if boxes is None else len(boxes)
    kp_person_count = 0
    kp_visible = []
    if kpts is not None and getattr(kpts, 'data', None) is not None:
        arr = kpts.data.cpu().numpy()
        kp_person_count = int(arr.shape[0]) if arr.ndim >= 3 else 0
        for person in arr:
            visible = int(np.sum(person[:, 2] >= 0.25)) if person.shape[1] >= 3 else 0
            kp_visible.append(visible)
    return {
        'detections': int(det_count),
        'keypoint_persons': kp_person_count,
        'visible_keypoints_mean': round(float(statistics.mean(kp_visible)), 2) if kp_visible else 0.0,
    }


def run_benchmark(video_path, model_path, max_people, frames_per_case, stride, imgsz, conf, repeats, canvas_w, canvas_h):
    from ultralytics import YOLO

    source_frames = read_frames(video_path, frames_per_case, stride)
    model = YOLO(str(model_path))
    warmup_frame = synthesize_people(source_frames[0], 1, canvas_w=canvas_w, canvas_h=canvas_h)
    model.predict(source=[warmup_frame], imgsz=imgsz, conf=conf, verbose=False, device='cpu')
    rows = []
    for people in range(1, max_people + 1):
        frames = [synthesize_people(frame, people, canvas_w=canvas_w, canvas_h=canvas_h) for frame in source_frames]
        elapsed_runs = []
        summarized_runs = []
        for _ in range(max(1, repeats)):
            started = time.perf_counter()
            results = model.predict(
                source=frames,
                imgsz=imgsz,
                conf=conf,
                verbose=False,
                device='cpu',
            )
            elapsed_runs.append(time.perf_counter() - started)
            summarized_runs.append([summarize_result(result) for result in results])
        median_idx = sorted(range(len(elapsed_runs)), key=lambda idx: elapsed_runs[idx])[len(elapsed_runs) // 2]
        elapsed = elapsed_runs[median_idx]
        per_frame = summarized_runs[median_idx]
        detected_counts = [item['detections'] for item in per_frame]
        keypoint_counts = [item['keypoint_persons'] for item in per_frame]
        visible_means = [item['visible_keypoints_mean'] for item in per_frame if item['visible_keypoints_mean'] > 0]
        frame_count = len(frames)
        fps = frame_count / elapsed if elapsed > 0 else 0.0
        rtt_4s = frame_count / max(fps, 1e-9)
        rows.append({
            'people': people,
            'frames': frame_count,
            'canvas': f'{canvas_w}x{canvas_h}',
            'imgsz': imgsz,
            'conf': conf,
            'repeats': max(1, repeats),
            'elapsed_sec': round(elapsed, 4),
            'elapsed_min_sec': round(min(elapsed_runs), 4),
            'elapsed_max_sec': round(max(elapsed_runs), 4),
            'server_fps_pose_only': round(fps, 2),
            'estimated_4s_chunk_rtt_sec': round(rtt_4s, 3),
            'detected_people_mean': round(float(statistics.mean(detected_counts)), 2) if detected_counts else 0.0,
            'detected_people_min': int(min(detected_counts)) if detected_counts else 0,
            'detected_people_max': int(max(detected_counts)) if detected_counts else 0,
            'keypoint_people_mean': round(float(statistics.mean(keypoint_counts)), 2) if keypoint_counts else 0.0,
            'visible_keypoints_mean': round(float(statistics.mean(visible_means)), 2) if visible_means else 0.0,
        })
    return rows


def write_report(rows, output_json, output_md):
    output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'updated_at': now(),
        'benchmark_type': 'synthetic tiled sample-fall pose throughput',
        'skeleton_mode_limit': 20,
        'limitations': [
            '정확도 라벨 검증이 아니라 처리량/검출 안정성 벤치마크입니다.',
            '동일 인물을 화면에 타일링한 합성 조건이라 실제 교차/가림/거리 변화보다 단순합니다.',
            '운영 실시간 RTT는 네트워크, 브라우저 인코딩, 큐 길이에 따라 추가로 변합니다.',
        ],
        'rows': rows,
    }
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [
        '# 다중 인원 프레임 처리 벤치마크',
        '',
        f'- 업데이트: {payload["updated_at"]}',
        f'- 입력: sample-fall 영상을 1~{max([row["people"] for row in rows], default=0)}명으로 타일링한 합성 프레임',
        '- 목적: 정확도 확정이 아니라 인원 증가에 따른 pose 처리량/FPS/RTT 경향 확인',
        '',
        '| 인원 | pose FPS | 4초 청크 추정 RTT | 평균 검출 인원 | 검출 범위 | 평균 keypoint 인원 | 평균 visible KP |',
        '|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        lines.append(
            f"| {row['people']} | {row['server_fps_pose_only']:.2f} | {row['estimated_4s_chunk_rtt_sec']:.3f}s | "
            f"{row['detected_people_mean']:.2f} | {row['detected_people_min']}~{row['detected_people_max']} | "
            f"{row['keypoint_people_mean']:.2f} | {row['visible_keypoints_mean']:.2f} |"
        )
    if rows:
        unstable = [
            row for row in rows
            if row['people'] >= 5
            and abs(float(row['detected_people_mean']) - float(row['people'])) / max(1.0, float(row['people'])) > 0.25
        ]
        acceptable = [
            row for row in rows
            if row['people'] >= min(20, max([r['people'] for r in rows], default=5))
            and row['server_fps_pose_only'] >= 4.0
            and row['detected_people_mean'] >= row['people'] * 0.60
        ]
        if acceptable and unstable:
            recommendation = '20명 조건에서도 pose 처리량은 충분하지만, 5명 이상부터 과검출/누락이 커집니다. 화면 표시 한계 테스트는 통과했지만 상용 person별 판정은 1~2명 보증, 5명 hard limit, 20명은 연구/시연 한계로 보는 것이 안전합니다.'
        elif acceptable:
            recommendation = '20명 조건에서도 4fps 실시간 샘플링 처리량 자체는 가능 범위입니다. 다만 검출 누락과 ID 유지율은 실제 다중 인원 영상으로 별도 검증해야 합니다.'
        else:
            recommendation = '20명 조건에서는 검출/처리량 여유가 충분하지 않습니다. 상용 운영은 인원 제한, 카메라 분리, ROI 분리가 필요합니다.'
    else:
        recommendation = '벤치마크 결과가 없습니다.'
    lines.extend([
        '',
        '## 권장 판단',
        '',
        recommendation,
        '',
        '## 한계',
        '',
        '- 이 수치는 합성 벤치마크이며, 낙상 정확도/ID 유지율은 실제 다중 인원 라벨 영상으로 따로 측정해야 합니다.',
        '- 운영 RF-Dual 경로는 아직 대표 인물 timeseries를 사용하므로, 20명 skeleton 표시가 가능해도 20명 person별 낙상 판정이 완료됐다는 뜻은 아닙니다.',
    ])
    output_md.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', default=str(DEFAULT_VIDEO))
    parser.add_argument('--model', default=str(DEFAULT_MODEL))
    parser.add_argument('--max-people', type=int, default=20)
    parser.add_argument('--frames', type=int, default=24)
    parser.add_argument('--stride', type=int, default=3)
    parser.add_argument('--imgsz', type=int, default=320)
    parser.add_argument('--conf', type=float, default=0.15)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--canvas-w', type=int, default=1280)
    parser.add_argument('--canvas-h', type=int, default=720)
    parser.add_argument('--output-json', default=str(OUT_DIR / 'multiperson_frame_benchmark.json'))
    parser.add_argument('--output-md', default=str(OUT_DIR / 'multiperson_frame_benchmark.md'))
    args = parser.parse_args()
    rows = run_benchmark(
        Path(args.video),
        Path(args.model),
        max(1, args.max_people),
        max(1, args.frames),
        max(1, args.stride),
        args.imgsz,
        args.conf,
        max(1, args.repeats),
        max(320, args.canvas_w),
        max(240, args.canvas_h),
    )
    write_report(rows, Path(args.output_json), Path(args.output_md))
    print(json.dumps({'ok': True, 'rows': rows, 'output_json': args.output_json, 'output_md': args.output_md}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
