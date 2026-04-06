# 3-Level 라벨 체계 + 데이터 수집 전략 수립

- **ID**: 009
- **날짜**: 2026-04-06
- **유형**: 설계 + 기능 추가

## 작업 요약
3-Level 라벨 체계(Level 1 binary, Level 2 posture 6-class, Level 3 optional tags)를 설계하고, 클래스별 데이터 수집 목표·hard-case 세트·sit/lie 세부 프로토콜을 정의했다. 설계 문서(`docs/label-system-data-strategy.md`)를 작성하고, video_analysis.py에 라벨 상수·intake 디렉토리 헬퍼·데이터 수집 현황 조회 메서드를 추가했다.

## 변경 파일 목록

### 신규 파일
- `docs/label-system-data-strategy.md` — 3-Level 라벨 체계 설계서, sit/lie 세부 프로토콜, 데이터 수집 전략, hard-case 세트 정의, intake 디렉토리 구조

### 수정 파일
- `src/model/struct/video_analysis.py`
  - `_LABEL_L1_CLASSES`, `_LABEL_L2_CLASSES`, `_LABEL_L3_TAGS` — 라벨 체계 상수
  - `_HARD_CASE_CATEGORIES` — hard-case 카테고리 정의
  - `_DATA_TARGETS` — 클래스별 최소 데이터 목표
  - `_L1_TO_L2_BOOTSTRAP` — L1→L2 부트스트랩 매핑
  - `_intake_base_dir()` — intake 루트 경로 반환
  - `_ensure_intake_dirs()` — L1/L2/hard-case 디렉토리 일괄 생성
  - `_intake_class_counts()` — 클래스별 비디오 파일 수 조회
  - `_intake_data_status()` — 목표 대비 수집 현황 반환
