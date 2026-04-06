# KTH Action Recognition Dataset 다운로드 및 클립 변환

- **ID**: 022
- **날짜**: 2026-04-06
- **유형**: 인프라

## 작업 요약
`scripts/download_kth_action.py`를 실행하여 KTH Action Recognition Dataset에서 walking/running 영상을 다운로드하고 4초 클립으로 분할하여 intake 디렉토리에 배치했다.

## 수행 결과
- walking.zip → intake/walk/: 81 clips
- jogging.zip → 스킵 (이미 81 clips 존재)
- running.zip → intake/run/: 80 clips
- **총 161 신규 클립 추가**

## 변경 파일 목록
- `_appdata/data/data/training/intake/walk/`: 81 clips 추가
- `_appdata/data/data/training/intake/run/`: 80 clips 추가
