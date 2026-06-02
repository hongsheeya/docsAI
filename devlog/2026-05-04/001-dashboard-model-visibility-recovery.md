# 대시보드 모델 표시 복구

- **ID**: 001
- **날짜**: 2026-05-04
- **유형**: 버그 수정

## 작업 요약
대시보드가 실제 운영 모델 연결 상태와 무관하게 `RF-Dual`로 보이거나, 모델 경로가 UI에 드러나지 않아 "모델이 사라진 것처럼" 보이던 문제를 정리했다. 실제 런타임/프로토타입 상태를 기준으로 엔진 라벨을 표시하고, fallback 여부와 모델 경로를 화면에 노출하도록 수정했다.

## 원문 요청사항
```text
또 모델이 없어진거 같은데 찾아서 고쳐내
```

## 변경 파일 목록
- `src/app/page.dashboard/view.ts`
  - `currentEngineLabel()`이 분석 결과 또는 `prototypeInfo.analysis_engine_summary.current_runtime.label`을 우선 사용하도록 수정
  - 모델 준비 상태/문구/경로 helper 추가
- `src/app/page.dashboard/view.pug`
  - 운영 모델 카드에 ready/fallback/missing 상태 배지 추가
  - weights path 노출 추가
  - 분석 결과의 모델 런타임 카드에 `rf_model_path`, `posture_classifier`, 추출/검출 프레임 정보 표시 추가

## 검증
- `wiz project build --project=main` 성공
- `view.ts`, `view.pug` 진단 오류 없음

## 참고
현재 워크스페이스에서는 RF/XG 모델 산출물 파일이 직접 검색되지 않았다. 이번 수정은 실제 파일 유무와 관계없이, 대시보드가 현재 상태를 숨기지 않고 정확히 보여주도록 하는 복구이다.
