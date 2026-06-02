# Next Presentation Bookmark

작성일: 2026-06-01

이 문서는 다음 발표자료 갱신 시 기준점으로 사용한다. 사용자가 “발표자료 갱신”을 요청하면, 이전 전체 히스토리를 다시 늘어놓기보다 이 시점 이후의 개선사항을 중심으로 정리한다.

## 발표 기준점

이번 기준점은 2026-06-01 작업부터다.

- 표정 보조 모델 검증 및 외부 AI-Hub 82 Docker 모델 비교
- 하체 가림 + 수직 가림 보조 자세 모델
- skeleton/privacy 모드 적용
- 실시간/업로드 결과 표시 일치
- 다중 파일/압축 업로드 기반 학습 데이터 intake 확장
- 발표 중심: 표정 모델과 가림 전처리 모델이 실제 낙상 판단에 어떤 보조 근거를 주는지

## 현재까지 반영된 핵심 수치

- 자세/행동 모델: 5-class sequence group macro F1 0.9293, accuracy 0.9216
- 가림 증강 윈도우: 2,320개
- 수직 가림 증강:
  - 정적 stand/sit/lie 각 120개
  - 시퀀스 walk/run/sit/lie 각 160개
- 주요 약점:
  - lie recall 0.8465
  - lie -> stand 31건, lie -> sit 29건
- 표정 보조 모델 초기 검증:
  - 기존 100-sample quick validation 기준 낙상 판정 F1 개선은 제한적
  - 얼굴 미검출이 많아 표정 모델은 단독/강한 가중치가 아니라 약한 보조 근거로 유지

## 다음 발표에서 강조할 흐름

1. 교수님 개선 요청: 프라이버시 skeleton 표시, 가림 대응, 표정 기반 상태 분석 가능성 검토
2. 파이프라인: 영상 -> skeleton/pose -> 낙상 RF/XGBoost -> 자세/행동 -> 가림 보조 -> 표정 보조 -> 최종 판단 근거
3. 가림 모델: 하체 가림뿐 아니라 벽/문틀 같은 수직 가림까지 증강
4. 표정 모델: 얼굴이 보일 때만 상태 근거를 추가하고, 얼굴 미검출은 감점하지 않음
5. 데이터 intake: 업로드 모드에서 여러 파일/압축 파일을 한 번에 등록해 라벨링/재학습 루프 단축
6. 한계: 실제 수직 가림 영상, 실제 낙상 직전/직후 표정 데이터, 고령자/병실 카메라 데이터가 아직 부족

## 발표자료에서 줄일 내용

- AI-Hub 62 데이터는 현재 최종 모델 기여가 작으므로 핵심 슬라이드에서 제외 가능
- 속도 정책/RTT 세부 튜닝은 이번 발표 중심이 아니면 제외
- 업로드/실시간을 다르게 처리한다는 표현은 제거. 업로드는 실시간 청크 재현 검증 용도로 설명

## 관련 산출물

- `/opt/app/project/main/outputs/model_optimization/vertical_occlusion_impact_20260601.md`
- `/opt/app/project/main/outputs/external_facial_model_aihub82_docker_review_20260601.md`
- `/opt/app/project/main/outputs/external_facial_model_aihub82_docker_test_20260601.md`
- `/opt/app/project/main/outputs/facial_aux_validation/external_aihub82_emotionnet_ab_smoke_20260601.md`
- `/opt/app/project/main/docs/bulk-upload-training-intake-plan.md`
