# E2E Integration Test Report

- **실행 일시**: 2026-04-06 01:44:53
- **서버**: http://localhost:3000
- **프로젝트**: main
- **테스트 영상**: FALL=/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상/Y/FY/00025_H_A_FY_C1/00025_H_A_FY_C1.mp4, NON_FALL=/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상/N/N/00005_H_A_N_C1/00005_H_A_N_C1.mp4

## 결과 요약

| 항목 | 수 |
|------|---|
| 전체 | 18 |
| ✅ PASS | 18 |
| ❌ FAIL | 0 |
| ⏭ SKIP | 0 |

## 상세 결과

| 우선순위 | 이름 | 결과 | 소요시간 | 상세 |
|---------|------|------|---------|------|
| P0 | prototype_info 정상 호출 | ✅ PASS | 0.25s | formats=['mp4', 'mov', 'avi', 'mkv', 'webm'], max=200MB |
| P0 | 정상 영상 업로드 (낙상 Y) | ✅ PASS | 4.35s | risk_score=0.825, saved=20260406014430-038f55fd89f2-00025_H_A_FY_C1.mp4 |
| P0 | 정상 영상 업로드 (비낙상 N) | ✅ PASS | 3.86s | risk_score=0.12, fall=False |
| P0 | 빈 파일 업로드 (0바이트) | ✅ PASS | 0.08s | 정상 거부: 비어 있는 파일은 분석할 수 없습니다. |
| P0 | 비지원 형식 업로드 (.txt) | ✅ PASS | 0.08s | 정상 거부: 지원하지 않는 영상 형식입니다. |
| P0 | 파일 필드 없는 업로드 | ✅ PASS | 0.08s | 정상 거부: 업로드된 영상 파일이 없습니다. |
| P1 | 손상된 파일 업로드 (랜덤 바이너리 .mp4) | ✅ PASS | 0.35s | heuristic fallback 적용됨 (runtime_key=heuristic-fallback) |
| P1 | 피드백 — 잘못된 predicted_label | ✅ PASS | 0.08s | 정상 거부: 예측 라벨 정보가 올바르지 않습니다. |
| P1 | 피드백 — 잘못된 feedback_status | ✅ PASS | 0.08s | 정상 거부: 피드백 상태는 correct 또는 incorrect 이어야 합니다. |
| P1 | 피드백 — incorrect + actual_label 누락 | ✅ PASS | 0.08s | 정상 거부: 실제 정답 라벨(Y/N)을 선택해야 합니다. |
| P1 | 피드백 — 존재하지 않는 saved_name | ✅ PASS | 0.08s | 정상 거부: 원본 업로드 영상을 찾을 수 없습니다. |
| P2 | 모델 워밍업 (warmup_models) | ✅ PASS | 0.2s | warmed_up=['yolo-pose', 'rf-pose'], elapsed=122ms |
| P2 | 모델 타입별 업로드 — rf-pipeline | ✅ PASS | 4.65s | runtime_key=rf-pipeline-runtime, score=0.825 |
| P2 | 모델 타입별 업로드 — rf-pose | ✅ PASS | 4.59s | runtime_key=rf-pose-runtime, score=0.795 |
| P3 | 경로 탐색 방지 (saved_name = ../../etc/passwd) | ✅ PASS | 0.08s | 경로 탐색 차단됨: 원본 업로드 영상을 찾을 수 없습니다. |
| P3 | 비지원 확장자 (.exe) | ✅ PASS | 0.09s | 정상 차단: 지원하지 않는 영상 형식입니다. |
| P3 | mp4 확장자 + 텍스트 콘텐츠 (위장 파일) | ✅ PASS | 0.31s | heuristic fallback (heuristic-fallback) — 비디오 아닌 파일도 확장자만 검증 |
| P0 | 업로드 → 피드백 통합 경로 (correct feedback) | ✅ PASS | 4.33s | 업로드→피드백 성공: pred=N, final=N |
