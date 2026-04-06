| 날짜 | ID | 작업 내용 | 상세 |
| 2026-04-06 | 024 | sit/lie 학습 데이터 수집 및 XG-Posture 6클래스 재학습 (210샘플, CV F1=69.93%) | [상세](devlog/2026-04-06/024-sit-lie-data-collection.md) |
| 2026-04-06 | 023 | XG-Posture 재훈련 — KTH 데이터 통합, 141샘플 4-class, CV F1=86.19% | [상세](devlog/2026-04-06/023-xg-posture-retrain.md) |
| 2026-04-06 | 022 | KTH Action Recognition Dataset 다운로드 (walk 81 + run 80 = 161 clips) | [상세](devlog/2026-04-06/022-kth-data-download.md) |
| 2026-04-06 | 021 | 웹캠 모드 화면 표시 오류 수정 (CSS Grid grid-rows-1 + layout flex + h-full) | [상세](devlog/2026-04-06/021-webcam-display-grid-fix.md) |
| 2026-04-06 | 020 | 자세 분류 휴리스틱 부스트 및 학습 데이터 인프라 (FN-0024~0026) | [상세](devlog/2026-04-06/020-posture-heuristic-boost.md) |
| 2026-04-06 | 019 | 실시간 분석 UI 오버플로 수정 및 XG-Dual 신뢰성 개선 (FN-0019~0023) | [상세](devlog/2026-04-06/019-realtime-ui-xg-reliability.md) |
| 2026-04-06 | 018 | XG-Dual 검증 최적화 — 5초 윈도우 + walk/run/stand 휴리스틱 (FN-0018) | [상세](devlog/2026-04-06/018-xg-dual-verification-optimization.md) |
| 2026-04-06 | 017 | 실시간 분석 로그 사이드 패널 이동 (영상 하단→오른쪽 2컬럼 레이아웃) | [상세](devlog/2026-04-06/017-log-side-panel.md) |
| 2026-04-06 | 016 | 오버레이 6-class 행동분류 시각화 강화 (확률 바·아이콘·하이라이트) | [상세](devlog/2026-04-06/016-overlay-6class-visualization.md) |
| 2026-04-06 | 015 | 전체 시스템 성능 평가 프레임워크 구축 (XG-Fall/Posture 개별 + 시스템 + baseline 리포트) | [상세](devlog/2026-04-06/015-evaluation-framework.md) |
| 2026-04-06 | 014 | RF-Pose 단계적 삭제 (deprecate → shadow → hard delete 준비) | [상세](devlog/2026-04-06/014-rf-pose-staged-deprecation.md) |
| 2026-04-06 | 013 | HITL 피드백 재설계 — 2-Level (낙상 + 자세 6-class + 애매함 태깅) | [상세](devlog/2026-04-06/013-hitl-feedback-redesign.md) |
| 2026-04-06 | 012 | XG-Dual UI/API 결과 구조 변경 (posture_probs + decision_state + explain 표시) | [상세](devlog/2026-04-06/012-xg-dual-ui-api-integration.md) |
| 2026-04-06 | 011 | XG-Dual 추론 파이프라인 구현 (Fall+Posture 동시 추론 + decision arbitration) | [상세](devlog/2026-04-06/011-xg-dual-inference-pipeline.md) |
| 2026-04-06 | 010 | XG Guard 후처리 엔진 이식 (5-suppressor + temporal smoothing + decision arbitration) | [상세](devlog/2026-04-06/010-xg-guard-postprocessing.md) |
| 2026-04-06 | 009 | 3-Level 라벨 체계 + 데이터 수집 전략 수립 (상수·intake 헬퍼 구현) | [상세](devlog/2026-04-06/009-label-system-data-strategy.md) |
| 2026-04-06 | 008 | XG-Posture 6-class multiclass 학습 파이프라인 구축 | [상세](devlog/2026-04-06/008-xg-posture-multiclass-training.md) |
| 2026-04-06 | 007 | XG 피처 확장 10→37 + XG-Fall 추론/재학습 파이프라인 구현 | [상세](devlog/2026-04-06/007-xg-fall-feature-expansion.md) |
| 2026-04-06 | 006 | 공통 person timeseries 추출기 + 37-feature 윈도우 빌더 구축 | [상세](devlog/2026-04-06/006-common-timeseries-extractor.md) |
| 2026-04-06 | 005 | RF-Pose 피처 명세 문서화 + XG 듀얼 아키텍처 설계서 (37-feature, 6-class) | [상세](devlog/2026-04-06/005-xg-dual-architecture-design.md) |
| 2026-04-06 | 004 | E2E 통합 테스트 스위트 구축 (18 시나리오 전체 PASS) | [상세](devlog/2026-04-06/004-e2e-integration-test.md) |
| 2026-04-06 | 003 | 실시간 분석 성능 최적화 — RTT 프로파일링, 적응형 간격, 모델 워밍업, 프레임 샘플링 최적화 | [상세](devlog/2026-04-06/003-realtime-performance-optimization.md) |
| 2026-04-06 | 002 | 다중 자세 클래스 라벨 체계 설계 (6-class 스키마 + 피드백 UI + 마이그레이션 전략) | [상세](devlog/2026-04-06/002-multiclass-posture-design.md) |
| 2026-04-06 | 001 | RF-Pose 25-feature HITL 학습 파이프라인 강화 (자동 재학습 트리거 + A/B 비교) | [상세](devlog/2026-04-06/001-rf-pose-hitl-pipeline.md) |
| 2026-04-03 | 017 | RF/XGBoost/RF-Pose 학습 방법 상세 분석 + 추가 자세(걷기·뛰기·앉기·눕기·서기) 학습 가능성 검토 | [상세](devlog/2026-04-03/017-model-training-analysis-pose-feasibility.md) |
| 2026-04-03 | 016 | 피드백 클릭 수정, 4초 윈도우, 로그 삭제, 오버레이 피처, WASM 경고 (FN-0025~0029) | [상세](devlog/2026-04-03/016-feedback-window-log-overlay-wasm.md) |
| 2026-04-03 | 015 | XGBoost 기본 모델 전환, UI 통일화, 실시간 로그/팝업 구현 (FN-0017~0024) | [상세](devlog/2026-04-03/015-xgboost-main-model-ui-realtime-log.md) |
| 2026-04-03 | 014 | 웹캠 UX 전면 개선 — Bbox 비활성화, 화면 대형화, 실시간 오버레이, 휴리스틱 fallback 복합 수정 (FN-0011~0016) | [상세](devlog/2026-04-03/014-webcam-ux-overlay-heuristic-fix.md) |
| 2026-04-03 | 013 | MediaPipe 포즈 감지 성능 최적화 — Lite 모델 + 12fps 스로틀 + ResizeObserver | [상세](devlog/2026-04-03/013-mediapipe-perf-optimization.md) |
| 2026-04-03 | 012 | RF 파이프라인 fallback 모델 피처 불일치 수정 — atomic write + 서버 모델 동기화 | [상세](devlog/2026-04-03/012-rf-pipeline-fallback-fix.md) |
| 2026-04-03 | 011 | COCO-17 스켈레톤 상수 중복 제거 (FN-20260403-0010) | [상세](devlog/2026-04-03/011-coco-skeleton-dedup.md) |
| 2026-04-03 | 010 | MediaPipe PoseLandmarker 클라이언트 사이드 포즈 추정 도입 (FN-20260403-0009) | [상세](devlog/2026-04-03/010-mediapipe-pose-landmarker.md) |
| 2026-04-03 | 009 | RF-Pose 모델 비활성 유지 결정 (FN-20260403-0008) | [상세](devlog/2026-04-03/009-rf-pose-keep-inactive.md) |
| 2026-04-03 | 008 | 카메라 하드웨어 줌 아웃 — CSS 스케일 제거 및 실제 카메라 제어 (FN-20260403-0007) | [상세](devlog/2026-04-03/008-camera-hardware-zoom.md) |
| 2026-04-03 | 007 | 웹캠 배율/핏 모드 조절 기능 추가 | [상세](devlog/2026-04-03/007-webcam-zoom-control.md) |
| 2026-04-03 | 006 | Threshold 동기화(43%→52%) 및 점수 계산식 동적 표시 (FN-20260403-0006) | [상세](devlog/2026-04-03/006-threshold-sync-score-detail.md) |
| 2026-04-03 | 005 | 실시간 RF 민감도 개선 — B(연속확인)+D(모션가드 강화) (FN-20260403-0005) | [상세](devlog/2026-04-03/005-realtime-sensitivity-bd-improvement.md) |
| 2026-04-03 | 004 | RF-Pose 2단계 분류 구조 — bbox 13 + pose 12 = 25 features RF 파이프라인 (FN-20260403-0004) | [상세](devlog/2026-04-03/004-rf-pose-2stage-classifier.md) |
| 2026-04-03 | 003 | page.dashboard view.ts 모듈 진단 오류 2건 정리 | [상세](devlog/2026-04-03/003-view-ts-module-resolution-fix.md) |
| 2026-04-03 | 003 | Keypoint 기반 자세 특징 추출 설계 및 구현 (FN-20260403-0003) | [상세](devlog/2026-04-03/003-keypoint-pose-feature-extraction.md) |
| 2026-04-03 | 002 | YOLOv8-Pose 모델 도입 — bbox + keypoints 동시 탐지 + 스켈레톤 시각화 (FN-20260403-0002) | [상세](devlog/2026-04-03/002-yolov8-pose-model-introduction.md) |
| 2026-04-03 | 001 | 대시보드 레이아웃 — 실시간 영상 풀와이드 + 컨트롤 하단 재배치 (FN-20260403-0001) | [상세](devlog/2026-04-03/001-dashboard-layout-webcam-fullwidth.md) |
| 2026-04-02 | 007 | 실시간 모드 Short-Clip 적응형 추론 구현 + E2E 테스트 (FN-0017) | [상세](devlog/2026-04-02/007-realtime-short-clip-implementation.md) |
| 2026-04-02 | 006 | 실시간 모드 RF 구조 분석 및 개선 방안 설계 (FN-0016) | [상세](devlog/2026-04-02/006-realtime-mode-analysis-design.md) |
| 2026-04-02 | 005 | XGBoost joblib 수정 + RF v4 전수감사 + 파이프라인/매뉴얼 v4 콘텐츠 (FN-0013~0015) | [상세](devlog/2026-04-02/005-xgb-joblib-v4-audit-content.md) |
| 2026-04-02 | 003 | RF v3 대규모 재학습 — 1000영상 + 정확도 최적화 (Acc 83.9→90.5%, threshold 0.25→0.42) | [상세](devlog/2026-04-02/003-rf-v3-retrain-1000-videos.md) |
| 2026-04-02 | 002 | RF threshold 0.25 UI 동기화 (파이프라인/대시보드 문구 수정, motion guard 조정) | [상세](devlog/2026-04-02/002-rf-threshold-ui-sync.md) |
| 2026-04-02 | 001 | 대시보드 UI 재구성, RF threshold 조정, 평가 스크립트 생성 (FN-0001~0011) | [상세](devlog/2026-04-02/001-dashboard-ui-threshold-eval-scripts.md) |
| 2026-04-01 | 012 | 대시보드 결과 UI 단순화 및 사용 설명서 정리 | [상세](devlog/2026-04-01/012-dashboard-result-simplification-and-manual-cleanup.md) |
| 2026-04-01 | 010 | 사용 설명서 페이지 생성, 개발자 매뉴얼 작성, 네비게이션 연동 | [상세](devlog/2026-04-01/010-user-manual-dev-manual-nav-update.md) |
| 2026-04-01 | 009 | RF HITL 학습 반영 경로 복구 | [상세](devlog/2026-04-01/009-rf-hitl-training-link-fix.md) |
| 2026-04-01 | 008 | HITL 재학습 time import 누락 수정 | [상세](devlog/2026-04-01/008-hitl-time-import-fix.md) |
| 2026-04-01 | 011 | RF fallback 런타임 payload 변수 누락 수정 | [상세](devlog/2026-04-01/011-rf-fallback-runtime-payload-fix.md) |
| 2026-04-01 | 007 | HITL 재학습 하드 타임아웃 제거 및 증분 최적화 | [상세](devlog/2026-04-01/007-hitl-retrain-no-timeout-incremental-optimization.md) |
| 2026-04-01 | 006 | 판단 근거 표시·Motion Gate·재학습 타임아웃 종합 개선 (FN-0030~0034) | [상세](devlog/2026-04-01/006-judgment-basis-motion-gate-retrain-fixes.md) |
| 2026-04-01 | 003 | 대시보드 파이프라인 고도화 (FN-0009~0022: bbox/리플레이/HITL/XGBoost/RF 튜닝) | [상세](devlog/2026-04-01/003-dashboard-pipeline-tuning-bbox-replay.md) |
| 2026-04-01 | 004 | Person-Feature(XGBoost) 런타임 병목 분석 및 인프로세스/캐시 최적화 | [상세](devlog/2026-04-01/004-person-feature-runtime-optimization.md) |
| 2026-03-30 | 011 | 분석 과정 시각화 — 사람 검출 트래킹 리플레이 (Canvas bbox overlay) | [상세](devlog/2026-03-30/011-detection-tracking-replay.md) |
| 2026-03-30 | 010 | 성능 최적화 — GPU 자동 감지, 단계별 타이밍 UI, reference_preview 안전검사 | [상세](devlog/2026-03-30/010-performance-timing-display.md) |
| 2026-03-30 | 009 | 사용설명서 ↔ 메인 페이지 양방향 네비게이션 추가 | [상세](devlog/2026-03-30/009-manual-main-navigation.md) |
| 2026-03-30 | 008 | 레거시 YOLO 분류 모델 전체 제거 (auto fallback: RF → Person-Feature) | [상세](devlog/2026-03-30/008-legacy-yolo-removal.md) |
| 2026-03-30 | 007 | view.ts 크리티컬 버그 수정 (fetch 에러 처리, 재귀→while, await 누락) | [상세](devlog/2026-03-30/007-view-ts-critical-bugs.md) |
| 2026-03-30 | 006 | RF/YOLO 정지 상태 오탐 수정 (motion guard) + 분석 시간 UI 표시 + 실시간 model_type 전달 | [상세](devlog/2026-03-30/006-motion-guard-false-positive-fix.md) |
| 2026-03-30 | 005 | 임계값 0.5 통일·엔진 동기화·HITL 보강·모델 비교 보고서 (FN-0001~0006) | [상세](devlog/2026-03-30/005-threshold-engine-hitl-comparison.md) |
| 2026-03-30 | 004 | 모델 정보 라우트 변수 누락 복구 및 RF 연결 상태 재정상화 | [상세](devlog/2026-03-30/004-model-info-route-recovery.md) |
| 2026-03-30 | 003 | RF 파이프라인 v2 기본 운영 모델 전환 및 표시 정합성 보정 | [상세](devlog/2026-03-30/003-rf-default-routing-and-visibility.md) |
| 2026-03-30 | 002 | HITL 재학습 경로 복구 및 실제 적용 모델 표시 강화 | [상세](devlog/2026-03-30/002-hitl-retraining-and-model-visibility.md) |
| 2026-03-30 | 001 | behavior_summary 메서드 충돌 수정 및 대시보드 라우팅 검증 | [상세](devlog/2026-03-30/001-behavior-summary-route-fix.md) |
| 2026-03-27 | 009 | 행동 분류 기준 정리 및 위험점수 설명 추가 | [상세](devlog/2026-03-27/009-behavior-riskscore-explanation.md) |
| 2026-03-27 | 008 | 업로드 분석 모델 라우팅 복구 및 오탐 방지 게이트 적용 | [상세](devlog/2026-03-27/008-upload-model-routing-fix.md) |
| 2026-03-27 | 007 | 실시간 분석 성능 종합 검토 및 지연 시간 측정 | [상세](devlog/2026-03-27/007-realtime-performance-review.md) |
| 2026-03-27 | 006 | 낙상영상 검증 결과 11건 삭제 및 관리자 UI 정리 | [상세](devlog/2026-03-27/006-validation-report-removal.md) |
| 2026-03-27 | 005 | 행동 분류 이진화 및 fallback 제거 | [상세](devlog/2026-03-27/005-binary-behavior-classification.md) |
| 2026-03-27 | 004 | 실시간 webm 청크 헤더 문제 수정 | [상세](devlog/2026-03-27/004-webm-realtime-chunk-fix.md) |
| 2026-03-27 | 003 | RF 파이프라인 추론 시간 최적화 (9.88s→4.71s, seek 기반 프레임 추출) | [상세](devlog/2026-03-27/003-inference-time-optimization.md) |
| 2026-03-26 | 031 | Validation 추가학습 최종 검증 및 종합 보고서 (FN-0024~0029) | [상세](devlog/2026-03-26/031-final-verification-summary.md) |
| 2026-03-26 | 030 | batch-001 추가학습 모델 웹 파이프라인 적용 (F1=0.7499 배포) | [상세](devlog/2026-03-26/030-pipeline-model-deployment.md) |
| 2026-03-26 | 029 | 추가학습 과적합 분석 — GroupKFold 검증 (진정 F1≈0.49, 데이터 누출 증명) | [상세](devlog/2026-03-26/029-overfitting-analysis-groupkfold.md) |
| 2026-03-26 | 028 | Validation 200건 학습 비교 (F1↓0.69) → batch-001 재학습 F1=0.7499 최종 채택 | [상세](devlog/2026-03-26/028-batch-all-200-training-comparison.md) |
| 2026-03-26 | 027 | Validation batch-001 100건 추가학습 (XGBoost F1=0.7141) | [상세](devlog/2026-03-26/027-batch001-additional-training.md) |
| 2026-03-26 | 026 | Validation 200건 균형 샘플링 설계 (Y100:N100, 171 prefixes) | [상세](devlog/2026-03-26/026-validation-sampling-design.md) |
| 2026-03-26 | 025 | 런타임·성능·표시 일치성 회귀 검증 | [상세](devlog/2026-03-26/025-runtime-regression-verification.md) |
| 2026-03-26 | 024 | 설명형 판단 근거 UI 고도화 | [상세](devlog/2026-03-26/024-explainable-analysis-basis-ui.md) |
| 2026-03-26 | 023 | 6종 행동 분류 런타임 연결 | [상세](devlog/2026-03-26/023-behavior-runtime-connection.md) |
| 2026-03-26 | 022 | 초고속 분석 프로파일 최적화 | [상세](devlog/2026-03-26/022-fast-runtime-optimization.md) |
| 2026-03-26 | 021 | 대시보드 모델 연동 및 0% 표시 복구 | [상세](devlog/2026-03-26/021-dashboard-model-runtime-fix.md) |
| 2026-03-26 | 020 | 웹 분석 파이프라인 person-feature 통합 | [상세](devlog/2026-03-26/020-web-pipeline-person-feature.md) |
| 2026-03-26 | 018 | bbox 궤적 기반 낙상 feature 추출 (194 windows, Y:82/N:112) | [상세](devlog/2026-03-26/018-fall-feature-extraction.md) |
| 2026-03-26 | 019 | 낙상 분류기 학습 (XGBoost best, F1=0.70, AUC=0.84) | [상세](devlog/2026-03-26/019-fall-classifier-training.md) |
|------|-----|----------|------|\n| 2026-03-26 | 017 | YOLO person detector fine-tune (mAP50=0.989, P=0.99, R=0.98) | [상세](devlog/2026-03-26/017-person-detector-finetune.md) |
| 2026-03-26 | 016 | Pseudo-label QC 도구 (tiny 10건 필터, fall 167 리뷰 이미지 생성) | [상세](devlog/2026-03-26/016-pseudo-label-qc-review.md) |
| 2026-03-26 | 015 | Pseudo-label YOLO person detect 데이터셋 생성 (270img, 282bbox) | [상세](devlog/2026-03-26/015-pseudo-label-dataset.md) |
| 2026-03-26 | 014 | YOLO person bbox 자동 추출 (11영상, 6058 bboxes, ByteTrack) | [상세](devlog/2026-03-26/014-person-bbox-extraction.md) |
| 2026-03-26 | 013 | 낙상 보호자 알람 실제 전송/다중 보호자/이력 조회 구현 | [상세](devlog/2026-03-26/013-guardian-alarm-system.md) |
| 2026-03-26 | 012 | /Sample 데이터 균형 재학습 및 /낙상영상 검증 (recall 100%) | [상세](devlog/2026-03-26/012-sample-retrain-balanced.md) |
| 2026-03-26 | 011 | YOLO 추론 분석 시간 최적화 (~60% 단축) | [상세](devlog/2026-03-26/011-analysis-time-optimization.md) |
| 2026-03-26 | 010 | 메인 화면 판단 중심 UI 리팩토링 (Insight 섹션 분리) | [상세](devlog/2026-03-26/010-dashboard-refactor-analysis-focus.md) |
| 2026-03-26 | 009 | /낙상영상 YOLO Classification 학습 (val 35%, 과적합) | [상세](devlog/2026-03-26/009-video-yolo-training.md) |
| 2026-03-26 | 008 | 과적합 검증 리포트(validation_report.json) 삭제 | [상세](devlog/2026-03-26/008-delete-validation-report.md) |
| 2026-03-26 | 007 | YOLO 모델 웹 통합 및 낙상영상 검증 (과적합 확인) | [상세](devlog/2026-03-26/007-yolo-model-integration-validation.md) |
| 2026-03-26 | 006 | Sample 데이터 기반 YOLO 학습 파이프라인 구축 | [상세](devlog/2026-03-26/006-sample-yolo-training-pipeline.md) |
| 2026-03-26 | 005 | 낙상 대응 단계별 응급 프로토콜 설계 반영 | [상세](devlog/2026-03-26/005-emergency-protocol-design.md) |
| 2026-03-26 | 004 | 좌측 사이드바 제거 및 전체 폭 레이아웃 전환 | [상세](devlog/2026-03-26/004-sidebar-removal-layout-update.md) |
| 2026-03-26 | 003 | 학습 데이터 수량과 모델 표시 기준 정비 | [상세](devlog/2026-03-26/003-dataset-model-visibility-refine.md) |
| 2026-03-26 | 002 | 피드백 저장 오류 및 파이프라인 진입 점검 보강 | [상세](devlog/2026-03-26/002-feedback-save-and-pipeline-route-fix.md) |
| 2026-03-26 | 001 | 신규 view.ts 모듈 진단 오류 4건 정리 | [상세](devlog/2026-03-26/001-fix-view-ts-module-diagnostics.md) |
| 2026-03-25 | 009 | 메인페이지 AI 파이프라인을 전용 서브페이지로 분리 | [상세](devlog/2026-03-25/009-pipeline-subpage-separation.md) |
| 2026-03-25 | 008 | 메인 분석 화면을 실행 중심으로 재배치 | [상세](devlog/2026-03-25/008-analysis-layout-focus.md) |
| 2026-03-25 | 007 | 실시간 웹캠 프리뷰 표시 로직 복구 | [상세](devlog/2026-03-25/007-webcam-preview-recovery.md) |
| 2026-03-25 | 006 | 업로드 분석 진단 메모와 품질 이슈 노출 | [상세](devlog/2026-03-25/006-upload-analysis-diagnostics.md) |
| 2026-03-25 | 005 | 학습 데이터 요약과 현재 모델 설명 정비 | [상세](devlog/2026-03-25/005-training-data-model-summary-refresh.md) |
| 2026-03-25 | 002 | 랜딩형 메인페이지 디자인 리뉴얼 | [상세](devlog/2026-03-25/002-landing-mainpage-renewal.md) |
| 2026-03-25 | 001 | 실시간 분석 가능 범위 검토 및 모델 설명 반영 | [상세](devlog/2026-03-25/001-realtime-feasibility-and-model-explanation.md) |
| 2026-03-23 | 003 | 실제 SMS 사업자 포맷 고정 | [상세](devlog/2026-03-23/003-sms-provider-payloads.md) |
| 2026-03-23 | 004 | FCM·APNs 푸시 포맷 분리 | [상세](devlog/2026-03-23/004-fcm-apns-split-payloads.md) |
| 2026-03-23 | 005 | Validation 70/30 기반 6종 행동 분류 모델 분리 | [상세](devlog/2026-03-23/005-validation-behavior-model-split.md) |
| 2026-03-23 | 006 | 이벤트 후보구간 신뢰도 재검토 | [상세](devlog/2026-03-23/006-event-confidence-recalibration.md) |
| 2026-03-23 | 001 | 재학습 검토 및 위험 알림·119 팝업 프로토타입 보강 | [상세](devlog/2026-03-23/001-risk-alert-retraining-dashboard.md) |
| 2026-03-23 | 002 | 보호자 설정 저장·외부 게이트웨이·실제 클립 추출·6종 행동 분류 확장 | [상세](devlog/2026-03-23/002-guardian-gateway-clip-behavior.md) |
| 2026-02-21 | 001 | 기존 인프라 page 앱 전체 삭제 및 일반 서비스 샘플 page 앱 생성 | [상세](devlog/2026-02-21/001-sample-pages-rebuild.md) |
| 2026-03-19 | 001 | 연구과제 범위 및 KPI 정의 문서 작성 | [상세](devlog/2026-03-19/001-research-scope-kpi.md) |
| 2026-03-19 | 002 | 데이터 수집·IRB·보안 체계 설계 문서 작성 | [상세](devlog/2026-03-19/002-data-irb-security-plan.md) |
| 2026-03-19 | 003 | 혼합형 데이터셋 구축 계획 문서 작성 | [상세](devlog/2026-03-19/003-hybrid-dataset-plan.md) |
| 2026-03-19 | 004 | 전처리·행동표현 파이프라인 문서 작성 | [상세](devlog/2026-03-19/004-preprocessing-pipeline-plan.md) |
| 2026-03-19 | 005 | AI 행동 분석 모델 전략 문서 작성 | [상세](devlog/2026-03-19/005-ai-model-strategy.md) |
| 2026-03-19 | 006 | 엣지 디바이스·실시간 시스템 설계 문서 작성 | [상세](devlog/2026-03-19/006-edge-system-design.md) |
| 2026-03-19 | 007 | 성능평가·실증 프로토콜 문서 작성 | [상세](devlog/2026-03-19/007-evaluation-pilot-protocol.md) |
| 2026-03-19 | 008 | 연차별 추진체계·리스크 관리 문서 작성 | [상세](devlog/2026-03-19/008-governance-risk-plan.md) |
| 2026-03-19 | 009 | 제안서 문장·근거자료 보강 문서 작성 | [상세](devlog/2026-03-19/009-proposal-refinement.md) |
| 2026-03-19 | 010 | 메인페이지 구조 단순화 및 로그인 제거 | [상세](devlog/2026-03-19/010-mainpage-simplification.md) |
| 2026-03-19 | 011 | 기존 라우트를 메인페이지로 통합 | [상세](devlog/2026-03-19/011-route-mainpage-unification.md) |
| 2026-03-19 | 012 | 업로드 기반 영상 분석 UX 프로토타입 구현 | [상세](devlog/2026-03-19/012-upload-prototype-ux.md) |
| 2026-03-19 | 013 | 낙상·위급상황 분석 모델 인터페이스 정의 | [상세](devlog/2026-03-19/013-analysis-model-interface.md) |
| 2026-03-19 | 014 | 메인페이지 분석 결과 UI 작성 | [상세](devlog/2026-03-19/014-mainpage-result-ui.md) |
| 2026-03-19 | 015 | 카메라 연동 전환 계획 문서화 | [상세](devlog/2026-03-19/015-camera-transition-plan.md) |
| 2026-03-19 | 016 | 학습데이터 수령 전 준비사항 정리 | [상세](devlog/2026-03-19/016-training-data-prep.md) |
| 2026-03-19 | 017 | 영상 Y/N 베이스라인 학습 파이프라인 구축 | [상세](devlog/2026-03-19/017-video-baseline-training-pipeline.md) |
| 2026-03-19 | 018 | 낙상 분석 설명 강화 및 추가 학습 데이터 접수 UI 구현 | [상세](devlog/2026-03-19/018-fall-analysis-explanation-intake-ui.md) |
| 2026-03-20 | 001 | 시니어 행동 혼합형 데이터셋 구축 계획 수립 | [상세](devlog/2026-03-20/001-senior-dataset-blueprint.md) |
| 2026-03-20 | 002 | 오픈·실제·합성 데이터 수집 파이프라인 정의 | [상세](devlog/2026-03-20/002-data-collection-pipeline.md) |
| 2026-03-20 | 003 | 데이터 전처리·라벨링·품질관리 체계 설계 | [상세](devlog/2026-03-20/003-labeling-quality-system.md) |
| 2026-03-20 | 004 | AI 행동 분석 SW 아키텍처 설계 | [상세](devlog/2026-03-20/004-sw-architecture-yolo-pose.md) |
| 2026-03-20 | 005 | AI 행동 분석 모델 개발·검증 계획 수립 | [상세](devlog/2026-03-20/005-model-development-validation.md) |
| 2026-03-20 | 006 | 경량형 실시간 분석 디바이스 HW/SW 통합 계획 수립 | [상세](devlog/2026-03-20/006-edge-device-integration-plan.md) |
| 2026-03-20 | 007 | 분석 결과 검증 피드백 및 재학습 루프 추가 | [상세](devlog/2026-03-20/007-analysis-feedback-retrain-loop.md) |
| 2026-03-20 | 008 | HITL 피드백 저장 연결 보강 및 검증 | [상세](devlog/2026-03-20/008-hitl-feedback-linkage-validation.md) |
| 2026-03-27 | 001 | RF 파이프라인 모델 추가 및 모델 선택 UI 구현 | [상세](devlog/2026-03-27/001-rf-pipeline-model-selection.md) |
| 2026-03-27 | 002 | 데이터 품질 개선, 파이프라인 최적화, UI 리밸런싱 (FN-0007~0015) | [상세](devlog/2026-03-27/002-data-quality-pipeline-optimization.md) |
| 2026-04-01 | 001 | 타이밍 인프라 구축 및 분석 프로파일/모델옵션 정리 (FN-0001~0010) | [상세](devlog/2026-04-01/001-timing-profile-cleanup.md) |
| 2026-04-01 | 002 | UI 재구성, Bbox 오버레이, 서버 타이밍 분해 (FN-20260401-0001~0008) | [상세](devlog/2026-04-01/002-ui-restructure-bbox-timing.md) |
| 2026-04-01 | 005 | 판단 근거 정렬·임계값 정합성·UI/파이프라인 전면 개선 (FN-0023~0029) | [상세](devlog/2026-04-01/005-judgment-threshold-ui-pipeline-overhaul.md) |
| 2026-04-02 | 001 | 대시보드 UI 재구성, threshold 변경, 평가 스크립트 생성 (FN-0001~0011) | [상세](devlog/2026-04-02/001-dashboard-ui-threshold-eval-scripts.md) |
| 2026-04-02 | 002 | RF Threshold UI 동기화 및 Motion Guard 보정 | [상세](devlog/2026-04-02/002-rf-threshold-ui-sync.md) |
| 2026-04-02 | 004 | XGBoost Fallback 수정 + RF v4 피처 개선 + 판단근거 짝수 표시 | [상세](devlog/2026-04-02/004-xgb-fix-rf-v4-features.md) |
| 2026-04-06 | 019 | 실시간 분석 UI 오버플로 수정 및 XG-Dual 신뢰성 개선 (FN-0019~0023) | [상세](devlog/2026-04-06/019-realtime-ui-xg-reliability.md) |
| 2026-04-06 | 020 | 자세 분류 휴리스틱 부스트 및 학습 데이터 인프라 (FN-0024~0026) | [상세](devlog/2026-04-06/020-posture-heuristic-boost.md) |
