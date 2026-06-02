# 발표 슬라이드 6가지 수정

- **ID**: 005
- **날짜**: 2026-04-27
- **유형**: 기능 수정, UI 개선

## 작업 요약

발표 페이지(`page.presentation`)에서 교수님 피드백 기반 6가지 수정 사항을 적용했다.
비디오 Angular 보안 이슈 해결, 017 이미지 교체, fall/lie 구분 내용 추가, threshold 값 명시, 이슈 슬라이드 교체, 나레이션 스크립트 동기화.

## 변경 파일 목록

### view.pug
- `[src]` → `[attr.src]`: Angular 보안 sanitizer가 video src를 `unsafe:`로 차단하는 문제 해결

### view.ts
- **슬라이드 3 (RF-Dual 아키텍처)**: 기존 "장점 ② 독립 개선" 그룹을 "fall vs lie 구분 방법" 그룹으로 교체
  - delta_y_max, height_std, final_height_ratio, fhr_rise_suppressor 원리 설명 추가
- **슬라이드 5 (XG-Posture 데이터)**: 샘플 이미지 5개를 017 원본으로 교체
  - stand/walk/run → 017-stand.jpg / 017-walk.jpg / 017-run.jpg (017 원본 bbox 크롭)
  - description 및 note 수정 (fall 클래스는 041 출처 명기)
- **슬라이드 7 (모델 성능)**: threshold 값 명시
  - `① 베이스라인 (default threshold)` → `① 베이스라인 (threshold=0.50)`
  - `② Recall-tuned (threshold 낮춤)` → `② Recall-tuned (threshold=0.35)`
  - `③ 최종 (FP 억제 guard 추가)` → `③ 최종 (threshold=0.35 + guard)`
  - "현재 운영 threshold" 행 제거
- **슬라이드 8~9 교체 → 단일 슬라이드 8**:
  - "발견된 이슈" + "수정 결과" (2장) 삭제
  - "현재 한계 — stand 데이터 불균형" (1장) 신규 추가
  - 배지 번호 8→9→10→11로 재정렬

### view.scss
- `.data-samples-grid`: `repeat(auto-fit, minmax(160px, 1fr))` → `repeat(3, 1fr)` (2×3 고정 그리드)

### src/assets/pres/ (신규 이미지 3장)
- `017-stand.jpg` (51KB): VID_0006613, bbox 크롭, 직립 자세
- `017-walk.jpg` (66KB): VID_0006026, bbox 크롭, 보행 자세
- `017-run.jpg` (56KB): VID_0005582, bbox 크롭, 활동 자세

### devlog/2026-04-27/004-presentation-narration-script.md
- 슬라이드 번호 동기화 (13장→12장)
- 슬라이드 3: fall vs lie 구분 내용 추가
- 슬라이드 7: threshold=0.50 / 0.35 명시
- 슬라이드 8: stand 불균형 내용으로 교체
- 슬라이드 9~11: 번호 재정렬
