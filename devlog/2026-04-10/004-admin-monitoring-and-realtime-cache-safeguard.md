# 관리자 모니터링 UI 및 실시간 롤링 캐시 안전장치 추가

- **ID**: 004
- **날짜**: 2026-04-10
- **유형**: 기능 추가

## 작업 요약
최신 XG-Fall 평가 결과와 `suspected_actual_nonfall` 경계 사례를 관리자 화면에서 바로 확인할 수 있도록 `prototype_info`에 최신 평가 요약을 연결하고, 관리자 페이지에 모니터링 섹션을 추가했다. 또한 실시간 롤링 메모리가 순차 `chunk_n` 파일에서만 이어지도록 제한해, 세션 간 stale tail이 섞일 가능성을 차단했다.

## 변경 파일 목록

### video_analysis.py (model/struct)
1. `latest_xg_fall_eval` 요약 헬퍼 추가
   - 최신 `eval_xg-fall_*.json`에서 metrics / thresholds / band_counts / suspected 사례를 읽어 관리자 UI에 전달
2. 실시간 롤링 캐시 범위 제한
   - `chunk_(n)` 패턴을 파싱해 이전 청크와 연속인 경우에만 tail stitching 수행
   - 업로드형 파일명이나 다른 세션의 청크와 캐시가 섞이지 않도록 방어

### page.admin.analysis/view.pug
1. 최신 XG-Fall 검증 요약 카드 추가
   - recall / precision / F1 / accuracy
   - FN / FP 상태 표시
   - 밴드 분포 및 threshold 표시
   - `suspected_actual_nonfalls` 목록 표시

## 검증 상태
- 프로젝트 빌드: ✅
- 최신 XG-Fall 평가 리포트: `storage/training/fall-detection/evaluation/eval_xg-fall_20260410_083440.json`
- 검증 지표 유지: ✅ recall 1.0 / precision 1.0 / F1 1.0 / accuracy 1.0
- 관리자 API는 인증이 필요한 경로라 비로그인 curl 검증은 401 확인, UI 바인딩은 빌드 성공으로 검증
