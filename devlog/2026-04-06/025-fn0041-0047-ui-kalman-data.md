# FN-0041~0047: UI 개선, 칼만 필터 스켈레톤, 데이터 균형 재학습

- **ID**: 025
- **날짜**: 2026-04-06
- **유형**: 기능 추가 / UI 개선 / 데이터 인프라

## 작업 요약
7개 FN 작업을 일괄 수행: XG-Dual 기본 모드 전환, 웹캠 네비게이션 복원, 로그 스크롤 수정, 로그 행동 라벨 표시, 판단 근거 복원, 칼만 필터 스켈레톤 예측, 041 Validation 데이터셋 기반 6-class 균형 재학습.

## 변경 파일 목록

### view.ts (FN-0041, 0044, 0045, 0046)
- `selectedModelType` 기본값: `'person-feature'` → `'xg-dual'`
- 신규 `Kalman1D` 클래스 (constant-velocity 모델, Q_pos=0.0005, Q_vel=0.005, R=0.003)
- `kalmanFilters`, `KF_MAX_MISS=15`, `KF_VIS_THRESHOLD=0.15` 프로퍼티 추가
- `initKalmanFilters()`: 33개 랜드마크 × 2차원 필터 생성
- `drawMpPose()`: 가시 랜드마크 → predict+update(실선), 가림 랜드마크 → predict-only(점선/투명 원)
- `pushRealtimeLog()`: 자세 분류 라벨(서기/걷기/뛰기/앉기/눕기) 표시 + `basis`, `decisionState` 필드 추가

### view.pug (FN-0042, 0043, 0044, 0045)
- 웹캠 모드 네비게이션 헤더에 🔬 파이프라인 / 📖 설명서 버튼 추가
- 로그 패널 컨테이너에 `overflow-hidden` 클래스 추가 (스크롤 영역 제한)
- 로그 항목에 `entry.basis` 한줄 표시 추가
- 로그 상세 모달에 판단 근거 요약 + decision state 배지 추가

### 데이터 (FN-0047)
- 041 Validation 데이터셋에서 stand(45), fall(45), sit(25), lie(15) 추출
- 최종 intake: stand:55, walk:81, run:80, sit:55, lie:55, fall:65
- XG-Posture 재학습: 349샘플, CV F1_macro=0.6735 (6클래스 모두 활성)
- XG-Fall 재학습: 20샘플, CV F1=0.8296, AUC=0.8889

### 신규 스크립트
- `scripts/extract_balanced_data.py`: 041 Validation 데이터 추출
- `scripts/run_retrain_direct.py`: WIZ HTTP 우회 직접 재학습 실행
