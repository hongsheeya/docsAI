# 타이밍 인프라 구축 및 분석 프로파일/모델옵션 정리

- **ID**: 001
- **날짜**: 2026-04-01
- **유형**: 기능 추가 / 리팩토링

## 작업 요약
FN-20260331-0001~0010 전체 수행. fast 분석 프로파일/auto 모델 옵션 제거, XGBoost 단계별 타이밍 추가, E2E 타임라인 바, 업로드 시간 측정, 서버 타이밍 수집, localStorage 최적화, 실제 영상 위 검출 오버레이, 분석모드 표시 버그 수정, 레이턴시 감사 문서 작성.

## 변경 파일 목록

### 백엔드
- **src/model/struct/video_analysis.py**: fast 프로파일 삭제, _RF_*_FAST 변수 삭제, auto 모델 옵션 삭제, _profile_label() 헬퍼 추가, _analysis_profiles()/_model_options() 단순화, analyze_upload() 기본값 balanced/rf-pipeline, server_timing dict 추가 (file_save_sec, summary_load_sec, inference_sec, result_build_sec, total_server_sec), heuristic fast bonus 제거
- **scripts/yolo_fall_runtime.py**: _perf dict 추가 (model_load, yolo_tracking, feature_extract, xgboost_predict, total), 모든 early return 경로에 perf 포함

### 프론트엔드
- **src/app/page.dashboard/view.ts**: 기본값 balanced/rf-pipeline, @ViewChild detVideo 추가, e2eTiming 프로퍼티 추가, analyzePreparedFile E2E 타이밍 계측 (upload_start→upload_end→response_received→render_done), handleRealtimeChunk analysis_profile 'fast'→this.analysisProfile (2곳), persistLastAnalysis detection_frames 제외, setAnalysisProfile 동적 라벨, currentEngineLabel/Note auto 분기 제거, getStepTimings XGBoost 키 추가 (yolo_tracking, xgboost_predict), getE2ETimeline() 타임라인 세그먼트 메서드 추가, drawDetectionFrame 영상 프레임 배경 오버레이
- **src/app/page.dashboard/view.pug**: 분석 프로파일 단일일 때 고정 라벨, E2E 타임라인 바 UI (색상 세그먼트+레전드), 업로드 시간 표시, 검출 리플레이 영역에 hidden video 요소 추가
