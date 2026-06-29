#!/usr/bin/env python3
"""Write a practical feasibility report for four-corner camera tracking."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


PROJECT = Path('/opt/app/project/main')
OUT_DIR = PROJECT / 'outputs' / 'performance'


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def best_row(path: Path, people: int) -> dict:
    data = read_json(path)
    rows = data.get('rows') if isinstance(data.get('rows'), list) else []
    for row in rows:
        if int(row.get('people') or 0) == people:
            return row
    return {}


def estimate():
    realtime_320 = best_row(OUT_DIR / 'multiperson_frame_benchmark_20260625.json', 3)
    precise_640 = best_row(OUT_DIR / 'multiperson_frame_benchmark_20260625_640.json', 3)
    pose_fps_320 = float(realtime_320.get('server_fps_pose_only') or 145.3)
    pose_fps_640 = float(precise_640.get('server_fps_pose_only') or 35.97)
    cameras = 4
    server_fps_per_camera = 4
    required_pose_fps = cameras * server_fps_per_camera
    return {
        'updated_at': now(),
        'scenario': '4 corner cameras, one primary target, 4 seconds chunk, 4fps server sampling',
        'camera_count': cameras,
        'server_fps_per_camera': server_fps_per_camera,
        'required_pose_fps': required_pose_fps,
        'pose_capacity_320_fps': round(pose_fps_320, 2),
        'pose_capacity_640_fps': round(pose_fps_640, 2),
        'estimated_pose_load_320': round(required_pose_fps / max(pose_fps_320, 1e-9), 3),
        'estimated_pose_load_640': round(required_pose_fps / max(pose_fps_640, 1e-9), 3),
        'verdict': 'feasible_prototype_needs_real_4cam_validation',
        'summary': '처리량만 보면 4개 코너 카메라를 동시에 받아 한 대상 추적/분석은 가능합니다. 다만 운영 판정으로 쓰려면 시간 동기화, 카메라 보정, 동일 인물 ID 융합, 실제 4카메라 검증셋이 필요합니다.',
        'requirements': [
            '카메라별 timestamp 오차를 200ms 이하로 맞춥니다.',
            '각 카메라의 ROI와 바닥 평면 homography를 저장합니다.',
            '카메라별 local track_id를 global person_id로 묶습니다.',
            '동일 시점에 2개 이상 카메라가 보이면 keypoint visibility/confidence가 높은 view를 우선합니다.',
            '낙상 알림은 카메라별 결과를 OR로 합치지 않고, 동일 global person 이벤트로 cooldown 병합합니다.',
        ],
        'risks': [
            '카메라 간 ID switch가 생기면 같은 사람의 행동 이력이 끊길 수 있습니다.',
            '동기화가 안 맞으면 낙상 순간이 카메라별로 다른 chunk에 들어가 점수가 흔들립니다.',
            '4개 영상을 모두 640px로 돌리면 CPU 여유가 줄어 RTT p95 검증이 필요합니다.',
            '현재 수치는 합성/단일카메라 벤치 기반이라 실제 방 모서리 시점 데이터로 재검증해야 합니다.',
        ],
        'recommended_design': [
            '1단계: 카메라 4개를 독립 분석하고 frame timestamp와 camera_id를 결과에 붙입니다.',
            '2단계: 침대/방 바닥 좌표로 bbox foot point를 투영해 global track을 만듭니다.',
            '3단계: camera_id별 person_result를 global person_result로 합칩니다.',
            '4단계: fall_score는 최고 위험 view와 시간 인접 view의 weighted evidence로 결정합니다.',
            '5단계: UI는 한 사람 카드 하나만 표시하고, 상세에서 카메라별 근거를 펼칩니다.',
        ],
        'validation_plan': [
            '빈 방/1명/보호자 동행/부분 가림/침대 옆 낙상/바닥 낙상 시나리오를 4카메라로 촬영합니다.',
            '지표는 target recall, false alarm, global ID switch, camera dropout recovery, RTT p50/p95로 나눕니다.',
            '합격 기준은 target recall 95% 이상, p95 RTT가 chunk stride 이하, ID switch가 이벤트 판정을 깨지 않는 수준입니다.',
        ],
    }


def write_report(payload: dict, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [
        '# 4카메라 코너 추적/분석 가능성 검증',
        '',
        f"- 갱신: `{payload['updated_at']}`",
        f"- 조건: `{payload['scenario']}`",
        f"- 판정: `{payload['verdict']}`",
        '',
        '## 결론',
        '',
        payload['summary'],
        '',
        '## 처리량 추정',
        '',
        '| 항목 | 값 |',
        '| --- | ---: |',
        f"| 필요 pose 처리량 | {payload['required_pose_fps']} fps |",
        f"| 320px 기준 처리량 | {payload['pose_capacity_320_fps']} fps |",
        f"| 320px 예상 부하 | {payload['estimated_pose_load_320'] * 100:.1f}% |",
        f"| 640px 기준 처리량 | {payload['pose_capacity_640_fps']} fps |",
        f"| 640px 예상 부하 | {payload['estimated_pose_load_640'] * 100:.1f}% |",
        '',
        '## 필수 조건',
    ]
    lines.extend(f'- {item}' for item in payload['requirements'])
    lines.extend(['', '## 권장 구조'])
    lines.extend(f'- {item}' for item in payload['recommended_design'])
    lines.extend(['', '## 검증 계획'])
    lines.extend(f'- {item}' for item in payload['validation_plan'])
    lines.extend(['', '## 리스크'])
    lines.extend(f'- {item}' for item in payload['risks'])
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    payload = estimate()
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d')
    json_path = OUT_DIR / f'four_camera_tracking_feasibility_{stamp}.json'
    md_path = OUT_DIR / f'four_camera_tracking_feasibility_{stamp}.md'
    write_report(payload, json_path, md_path)
    print(json.dumps({'ok': True, 'json': str(json_path), 'md': str(md_path), **payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
