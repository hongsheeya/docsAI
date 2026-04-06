# 초고속 분석 프로파일 최적화

- **ID**: 022
- **날짜**: 2026-03-26
- **유형**: 성능 개선

## 작업 요약
`person-feature-runtime`의 전체 프레임 순회 병목을 줄이기 위해 `fast`/`balanced` 프로파일을 분리했다. 빠른 분석은 샘플링 기반 추적, 다운스케일, 초기 사람 검출 프리체크를 사용하도록 개선했고, 정밀 분석은 기존 전체 추적 흐름을 유지했다. 결과 화면에는 처리 프레임 수와 실제 소요 시간이 함께 노출되도록 반영했다.

## 변경 파일 목록
### 런타임
- `scripts/yolo_fall_runtime.py`
  - profile별 설정(`fast`/`balanced`) 추가
  - 초기 사람 검출 프리체크 추가
  - `vid_stride`, `imgsz`, 분석 구간 길이, window/stride를 profile별로 분리
  - `processed_frames`, `profile_config`, `track_summary` 출력 추가

### 서버 분석 로직
- `src/model/struct/video_analysis.py`
  - person-feature 호출 시 profile 전달
  - `analysis_speed_note`에 처리 프레임 수와 프로파일 반영
  - 분석 근거에 프로파일/처리 프레임/윈도우 수 표시
  - 분석 프로파일 설명과 목표 시간 갱신

## 테스트 결과
- 대표 낙상 샘플 비교
  - fast: 5.441초 / 52프레임 처리 / score 0.7057
  - balanced: 29.489초 / 600프레임 처리 / score 0.7573
- 빌드 성공 및 오류 없음
