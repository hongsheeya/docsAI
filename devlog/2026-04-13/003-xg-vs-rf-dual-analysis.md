# XG-Dual vs RF-Dual 성능 비교 분석 리포트 작성

- **ID**: 003
- **날짜**: 2026-04-13
- **유형**: 문서 업데이트

## 작업 요약

XG-Dual과 RF-Dual 두 파이프라인의 학습 알고리즘, 특징 추출, 판단 로직, 속도, 정확도, 자세별 성능을 실제 모델 파일에서 구조를 로드하여 수치 기반으로 비교 분석함. 11개 섹션의 상세 리포트를 작성하여 추천 시나리오까지 정리했음.

## 변경 파일 목록

### 신규 생성

| 파일 | 내용 |
|------|------|
| `devlog/2026-04-13/xg-dual-vs-rf-dual-analysis.md` | 11-section 상세 비교 분석 리포트 |

### 리포트 섹션 구성

| 섹션 | 내용 요약 |
|------|----------|
| 1. 학습 알고리즘 | RF (200 trees, unlimited depth, 13 features) vs XGBoost (200 trees, depth 6, lr 0.1, 43 features) |
| 2. 특징 추출 파이프라인 | XG: unified timeseries 37-feat / RF-Dual: bbox 통계 13-feat + XG-Posture 42-feat 2-pass |
| 3. 판단 로직 | XG: 9종 suppressor + 4 override / RF-Dual: stationary check 단순화 |
| 4. CV 정확도 | 동일: accuracy 0.905, recall 0.917 / AUC: RF 1.0 vs XG 0.889 |
| 5. Intake 평가 | XG-Dual 1.0 (21건) / RF-Dual 미실행 |
| 6. 자세별 성능 | XG-Posture 공유, CV 0.618 (stand/walk/run/fall=1.0, sit=0.981, lie=0.982) |
| 7. YOLO 패스 수 | XG: 1회 / RF-Dual: 2회 (YOLO + RF + YOLO + Posture) |
| 8. 속도 추정 | XG: 5~15초/~8초 청크 / RF-Dual: 4~12초/~6초 청크 |
| 9. Rolling cache | XG: 세션별 파일 영속화 / RF-Dual: 없음 |
| 10. 장단점 요약 | XG: 풍부한 시계열 맥락, 정교한 억제자 / RF: 빠른 추론, 단순 파이프라인 |
| 11. 추천 시나리오 | 실시간·엣지: RF-Dual / 아카이브·고정밀: XG-Dual |

## 주요 발견 사항

- 두 모델의 CV 정확도는 동일(0.905)이지만 AUC는 RF(1.0)가 높음
- XG-Fall은 43개 feature 중 상위 3개가 전체 중요도의 40% 이상 차지
- RF의 top-3 feature: `final_height_ratio`(24.76%), `delta_y_max`(21.74%), `aspect_ratio_std`(11.54%)
- XG-Posture의 자세 분류 CV 0.618은 프레임-단위 특성으로 인한 한계이며, 전이 구간(lie↔stand)에서 주로 오분류 발생
