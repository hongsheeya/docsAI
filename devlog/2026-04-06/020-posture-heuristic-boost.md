# 자세 분류 휴리스틱 부스트 및 학습 데이터 인프라 (FN-0024~0026)

- **ID**: 020
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
XG-Posture 6-class 모델의 walk/run/stand/sit 분류 정확도를 개선하기 위해 도메인 지식 기반 휴리스틱 부스트 후처리를 추가하고, 전이 매트릭스를 완화하며, KTH Action Recognition Dataset 기반 학습 데이터 수집 스크립트를 작성했다.

## 변경 파일 목록

### video_analysis.py (휴리스틱 부스트 + 전이 매트릭스)
- `_posture_heuristic_boost()` 메서드 추가 (~120줄):
  - Rule 1 (Stand→Walk): stillness < 0.6 + center_y_periodicity > 0.15 → walk 확률 부스트
  - Rule 2 (Walk→Run): step_period < 0.4 + speed_std > 0.015 + strong bounce → run 확률 부스트
  - Rule 3 (Stand→Sit): pose_knee_bend > 0.25 + tilt < 20° + lowered height → sit 확률 부스트
- `_infer_xg_dual`: 모델 predict 직후, pw_list 생성 전에 `_posture_heuristic_boost()` 호출
- `_POSTURE_TRANSITION_ALLOWED`: stand↔run 직접 전이 허용 (짧은 클립에서 run 감지 개선)

### scripts/download_kth_action.py (신규)
- KTH Action Recognition Dataset 자동 다운로드 + 클립 분할 스크립트
- walking/jogging → walk, running → run 매핑
- 4초 클립, 1초 오버랩, 비디오당 최대 3클립, 클래스당 최대 80클립

### 인프라 (디렉토리)
- intake 디렉토리 생성: fall, non-fall, stand, walk, run, sit, lie, hard-case/
- ffmpeg 설치 (비디오 분할용)
