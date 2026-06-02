# 실시간 세션 캐시 영속화 및 청크 스모크 테스트

- **ID**: 005
- **날짜**: 2026-04-10
- **유형**: 기능 추가

## 작업 요약
일일보고 작성 후 다음 단계로 실시간 `chunk_n` 흐름을 직접 검증했다. 먼저 프론트엔드가 `realtime_session_id`를 함께 보내도록 확장하고, 백엔드 XG-Dual rolling cache가 세션별 임시 파일(`/tmp/wiz_rt_cache_{session}.json`)에 저장되도록 변경해 HTTP 요청이 바뀌어도 인접 청크 간 tail stitching이 유지되게 했다.

이후 스모크 테스트에서 같은 세션의 연속 청크는 `rolling_stitched=9`로 정상 연결되고, 다른 세션은 독립적으로 `rolling_stitched=0 → 9` 흐름을 보여 세션 분리가 동작함을 확인했다. 다만 전체 영상을 연속 청크처럼 재전송한 비현실적 테스트이므로, 두 번째 청크 결과가 `non-fall`로 바뀌는 현상은 실제 웹캠 청크와 동일 해석이 아니며, stitching 자체의 동작 여부 확인용 결과로 해석해야 한다.

## 변경 파일 목록

### view.ts (page.dashboard)
1. `realtimeSessionId` 추가
2. 실시간 시작 시 세션 ID 생성, 종료 시 초기화
3. 청크 업로드 metadata에 `realtime_session_id` 추가

### video_analysis.py (model/struct)
1. `_infer_with_trained_model()`에 `realtime_context` 전달 경로 추가
2. `_infer_xg_dual()` rolling cache를 `session_id + chunk_id` 기반으로 동작하도록 변경
3. `/tmp/wiz_rt_cache_{session}.json` 파일 기반 세션 캐시 헬퍼 추가
4. `chunk_id`를 filename뿐 아니라 metadata에서도 읽도록 보강

## 검증 상태
- 프로젝트 빌드: ✅
- 실시간 스모크 테스트: ✅ 세션별 인접 청크 stitching 확인
- 오프라인 XG-Fall 재검증: `storage/training/fall-detection/evaluation/eval_xg-fall_20260410_085856.json`
- 검증 지표 유지: ✅ recall 1.0 / precision 1.0 / F1 1.0 / accuracy 1.0
