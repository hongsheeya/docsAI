# 041 낙상사고 데이터에서 walk/stand/sit 클립 자동 추출

- **ID**: 004
- **날짜**: 2026-04-07
- **유형**: 기능 추가

## 작업 요약
041 N(Normal) dataset 568개 mp4 영상에서 walk 200, stand 100, sit 100 = 총 400개 4초 클립을 자동 추출하였다. YOLO 기반 v1(CPU 너무 느림)과 optical flow 기반 v2(CCTV 임계값 미스매치)를 거쳐, frame-diff centroid tracking 기반 v3 스크립트로 최종 구현하여 약 88분만에 추출을 완료하였다. 기존 KTH walk 데이터 81개는 `_backup_kth_walk/`로 백업 처리하였다.

## 변경 파일 목록

### 신규 스크립트
| 파일 | 변경 내용 |
|------|----------|
| `scripts/extract_walk_stand_sit.py` | 041 N dataset에서 walk/stand/sit 4초 클립 자동 추출 스크립트 (frame-diff centroid tracking) |

### 데이터 변경
| 경로 | 변경 내용 |
|------|----------|
| `_appdata/storage/training/fall-detection/intake/walk/` | 0 → 200 (n041_* 클립 추가) |
| `_appdata/storage/training/fall-detection/intake/stand/` | 54 → 154 (n041_* 100개 추가) |
| `_appdata/storage/training/fall-detection/intake/sit/` | 55 → 155 (n041_* 100개 추가) |
| `_appdata/storage/training/fall-detection/intake/_backup_kth_walk/` | KTH walk 81개 보관 |
| `_appdata/storage/training/fall-detection/intake/_extract_report_fn0058.json` | 추출 리포트 |

## 기술 상세

### 분류 알고리즘 (v3 - frame-diff centroid tracking)
- 320×240 resize 후 연속 프레임 간 차분(frame diff) 계산
- 차분 영역의 centroid를 추적하여 total displacement 산출
- **Walk**: total centroid displacement > 25px
- **Stand**: displacement ≤ 25 AND diff region aspect ratio > 1.45
- **Sit**: displacement ≤ 25 AND aspect ratio ≤ 1.45

### 폐기된 접근법
| 버전 | 방식 | 폐기 사유 |
|------|------|----------|
| v1 | YOLO-based pose estimation | CPU ~1.5 clips/min, 400개 추출에 ~4.5시간 소요 예상 |
| v2 | Optical flow magnitude | CCTV 영상에서 flow magnitude 0.09~0.50으로 임계값 미스매치 |

### 성능
- v3 처리 속도: ~5 clips/min
- 전체 소요 시간: ~88분 (568 영상 스캔 → 400 클립 추출)
