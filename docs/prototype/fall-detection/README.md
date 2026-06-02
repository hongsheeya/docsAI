# Fall Detection Prototype

이 디렉토리는 낙상/위급상황 분석 프로토타입의 구현 방향과 전환 계획을 정리한다.

## 현재 운영 상태 (2026-06-01)

자세한 기준 문서는 [../../2026-06-01-current-status-and-training-pipeline.md](../../2026-06-01-current-status-and-training-pipeline.md)를 따른다.

- **RF-Fall v2 운영 적용 완료**: AI-Hub 71641 및 intake 기반 1,592 samples 학습
	- Class: non-fall 795 / fall 797
	- Feature: 65개 bbox + skeleton + occlusion-aware feature
	- Threshold sweep: best-F1 threshold 0.405 / confirm threshold 0.455
	- Metrics: best-F1 0.9337, confirm F1 0.9302
- **XG-Posture 5-class 운영 적용 완료, 추가 개선 필요**
	- Class: `stand / walk / run / sit / lie`
	- Active algorithm: `xgb_regularized`
	- Samples: 2,466
	- Feature: 105개
	- Group CV: accuracy 0.6602 / macro F1 0.6513
	- 현재 수치는 실시간/실환경 도메인 차이를 반영한 더 보수적인 grouped 검증 기준이다.
- **하체가림 보조 모델 적용**
	- ExtraTrees balanced auxiliary
	- Group CV accuracy 0.8663 / macro F1 0.8657
	- lower-body visibility가 낮거나 주 모델 confidence가 낮을 때 보조 근거로 사용한다.
- **표정/상태 보조 모델 적용**
	- AI-Hub 82 표정: MobileNetV3, macro F1 0.6198
	- AI-Hub 173 상태: MobileNetV3, macro F1 0.9054
	- 얼굴이 실제로 검출되지 않으면 감정 라벨을 사용하지 않고 `얼굴/표정 미검출`로 표시한다.
- **YOLO shadow test 완료**
	- YOLOv8n-pose: KP 검출률 93.06%, 평균 13.43ms
	- YOLO11n-pose: KP 검출률 91.67%, 평균 13.97ms
	- 현재는 YOLOv8n 운영 유지, YOLO11은 confidence 개선 후보로 병렬 검증한다.

## 문서 구성

- `routing-and-mainpage-plan.md` — 메인페이지 통합과 랜딩 구조 정리
- `camera-transition-plan.md` — 업로드 기반 구조를 실시간 카메라 입력으로 확장하기 위한 전환 계획
- `training-data-requirements.md` — 학습데이터 수령 전 준비사항과 요구 포맷

## RF-Dual 낙상 판단 기준

- **1차 판정**: RF-Fall v2가 65개 feature로 낙상 확률을 계산한다.
- **2차 해석**: XG-Posture가 5-class(`stand / walk / run / sit / lie`) 자세/행동을 분류한다.
- **하체가림 보조**: lower-body visibility가 낮으면 occlusion auxiliary와 guard feature로 stand/sit/lie를 보정한다.
- **표정/상태 보조**: 실제 얼굴이 보이고 신뢰도가 충분할 때만 표정/상태 점수를 보조 evidence로 붙인다.
- **최종 결정**: RF-Fall v2 확률 + XG-Posture + occlusion guard + arbitration 상태(`safe`, `posture_only`, `fall_suspected`, `fall_confirmed`)를 합쳐 낙상 여부를 정한다.

핵심 해석은 다음과 같다.

1. **RF-Fall v2는 빠른 경보 엔진**이다.
	 - `detection_rate`, `center_y_drop`, `height_drop_ratio`, `fall_kinematic_score`, `lying_skeleton_score` 같은 feature로 급격한 하강과 자세 붕괴를 본다.
2. **XG-Posture는 설명/억제 엔진**이다.
	 - walk/run처럼 이동량이 필요한 행동과 sit/lie처럼 형태가 중요한 행동을 분리한다.
	 - 현재 grouped macro F1은 0.6513이므로 실제 설치 각도 hard-case 수집과 재학습이 다음 우선순위다.
3. **하체가림 보조가 필요한 이유**
	 - 하체가 안 보이면 stand/sit/lie가 흔들리고 `미확인` 또는 `lie`로 쏠릴 수 있다.
	 - 상체 verticality, bbox 중심/높이, visibility, support stability feature로 보이는 정보 기반 보조 판단을 한다.
4. **표정/상태 모델이 필요한 이유**
	 - 표정은 낙상 판정 모델이 아니라, 위험 상태 설명을 풍부하게 만드는 보조 evidence다.
	 - 얼굴 미검출 시 감정 라벨을 사용하지 않는 것이 원칙이다.

## 청크 정책

- **현재 정책**
	- 실시간 웹캠: 4초 청크를 끊기지 않게 생성한다.
	- 업로드 분석: 실시간과 같은 4초 단위 분할 로그를 생성해 행동 변화 전후를 표시한다.
	- RTT가 튀어도 브라우저 큐에서 청크를 버리지 않고 순차 전송한다.
- **프레임 샘플링**
	- 실시간 서버 AI 추론은 4fps 기준으로 최대 16프레임을 본다.
	- 화면 오버레이는 60fps 표시를 목표로 하지만, 서버 YOLO/pose 추론과 분리한다.
- **롤백 포인트**
	- 정책 버전은 `legacy-rf-dual-v1`로 되돌릴 수 있도록 버전 문자열로 분리해 두었다.

## 로그 정책

- 모든 로그에 **한 줄 설명**(`구간 · 위험도 · 자세 · 상태 · 엔진`)을 붙인다.
- 업로드 분석도 전체 결과 외에 **분할 로그**를 함께 생성·표시한다.
- 업로드 분석 결과는 메타 JSON에 마지막 분석 요약과 분할 로그가 함께 기록된다.
