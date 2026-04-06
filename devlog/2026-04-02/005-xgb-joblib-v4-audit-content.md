# XGBoost joblib 수정 + RF v4 전수감사 + 파이프라인/매뉴얼 v4 콘텐츠

- **ID**: 005
- **날짜**: 2026-04-02
- **유형**: 버그 수정 + 문서 업데이트

## 작업 요약
1. FN-0013: XGBoost fallback 근본 원인 수정 — scikit-learn 설치, pickle→joblib 전환
2. FN-0014: RF v4 전수감사 — v2→v4, 16→13, 0.42→0.43 참조 일괄 교체
3. FN-0015: 파이프라인 페이지에 v4 Feature 상세/성능 지표 섹션 추가, 매뉴얼 AI 파이프라인 섹션 v4 업데이트

## 변경 파일 목록

### FN-0013: XGBoost Fallback 근본 수정
- `scripts/yolo_fall_runtime.py`: `import joblib` 추가, `get_cached_classifier()`에서 `pickle.load(f)` → `joblib.load(classifier_path)` 변경
- **환경**: `pip install scikit-learn` (1.8.0) — conda env Python 3.14에 설치

### FN-0014: RF v4 전수감사 (약 25개소)
- `src/model/struct/video_analysis.py`: 
  - threshold 주석 0.42→0.43 (2개소)
  - runtime_label, model_name, metric_note, split_note 등 ~20개소 v2→v4
  - 특징 수 "16개"→"13개" 전체 교체
  - 모델 비교 테이블 업데이트
- `src/app/page.manual/view.pug`: "판단 근거" 설명 업데이트

### FN-0015: 파이프라인/매뉴얼 v4 콘텐츠
- `src/app/page.pipeline/view.pug`:
  - RF 파이프라인 흐름에 Motion Guard 단계 추가
  - "RF v4 특징(Feature) 상세" 섹션 신규 추가 (13개 특징 중요도·설명·성능 지표)
  - feature_count 기본값 16→13 수정
- `src/app/page.manual/view.pug`:
  - AI 파이프라인 섹션에 "RF v4 분석 특징 (13개)" 서브섹션 추가
  - "분석 결과 카드 해석" 서브섹션 추가 (위험도 점수, Y축 하강, 가속도, 자세 높이, 종횡비 해설)
