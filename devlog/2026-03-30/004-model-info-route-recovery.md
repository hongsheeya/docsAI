# 모델 정보 라우트 변수 누락 복구 및 RF 연결 상태 재정상화

- **ID**: 004
- **날짜**: 2026-03-30
- **유형**: 버그 수정

## 작업 요약
RF 파이프라인 v2를 기본 운영 모델로 전환하는 과정에서 `src/model/struct/video_analysis.py`의 `_trained_model_info()` 내부에 `split_note`, `metric_source`, `evaluation_source` 초기화가 빠져 있었다. 이 때문에 모델 요약을 생성하는 라우트가 런타임에서 예외를 발생시키며, 화면에서는 모델 연결이 해제된 것처럼 보였다. 누락 변수를 복구하고 RF 메타 경로 기준 문구까지 함께 정리해 모델 정보가 다시 정상 노출되도록 수정했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - `_trained_model_info()`에 누락된 메타 변수 초기화 추가
  - RF 메타 표시 시 `rf-runtime-structure` / `RF Runtime Structure` 문구 정리
- `devlog.md`
  - 2026-03-30 작업 요약 행 추가

## 검증
- `_trained_model_info()` 직접 호출 검증: 예외 없이 `rf-pipeline-runtime` 반환 확인
- normal build 성공
