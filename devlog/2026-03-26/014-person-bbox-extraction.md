# Person Bbox 자동 추출 스크립트

- **ID**: 014
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
사전학습 YOLO11n (COCO person=class 0) + ByteTrack을 이용해 /낙상영상 11개 mp4에서 프레임별 person bbox를 자동 추출하는 스크립트를 작성하고 실행했다. 전 프레임(600/영상) 처리로 tracking 연속성을 확보하고, 총 6,058 bboxes / 53 unique tracks를 JSON으로 저장했다.

## 변경 파일 목록

### 신규 생성
- `scripts/extract_person_bbox.py`: YOLO person detection + ByteTrack tracking 스크립트
  - model.track(stream=True, persist=True) 사용, CPU 환경에서 ~15fps 처리
  - 영상별 JSON 출력 (frame_idx, track_id, x1/y1/x2/y2, confidence)
  - manifest.json으로 전체 요약 저장

### 생성된 데이터
- `storage/training/fall-detection/person-bbox/*.json`: 11개 영상별 bbox JSON
- `storage/training/fall-detection/person-bbox/manifest.json`: 전체 처리 요약

## 처리 결과
| 영상 | 라벨 | bbox수 | tracks | 감지 프레임 | 처리시간 |
|------|------|--------|--------|------------|---------|
| 00001_H_A_SY_C3 | Y | 377 | 10 | 332/600 | 38.8s |
| 00025_H_A_FY_C3 | Y | 701 | 7 | 449/600 | 38.0s |
| 00028_H_A_FY_C7 | Y | 557 | 2 | 549/600 | 39.0s |
| 00059_H_A_FY_C2 | Y | 499 | 4 | 480/600 | 39.4s |
| 00074_H_A_BY_C1 | Y | 394 | 5 | 393/600 | 39.3s |
| 00005_H_A_N_C4 | N | 601 | 2 | 600/600 | 39.1s |
| 00023_H_A_N_C1 | N | 439 | 2 | 439/600 | 37.5s |
| 00074_H_A_BY_C1 | N | 637 | 2 | 585/600 | 38.9s |
| 00095_H_A_N_C8 | N | 589 | 6 | 514/600 | 39.4s |
| 00110_H_A_N_C1 | N | 584 | 5 | 550/600 | 39.3s |
| 00216_H_D_N_C4 | N | 680 | 8 | 517/600 | 39.7s |
| **합계** | | **6,058** | **53** | | **431.4s** |
