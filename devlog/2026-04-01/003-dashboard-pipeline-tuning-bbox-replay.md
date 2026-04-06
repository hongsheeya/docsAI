# 대시보드 파이프라인 고도화 (FN-0009~0022)

- **ID**: 003
- **날짜**: 2026-04-01
- **유형**: 기능 추가

## 작업 요약
낙상 분석 대시보드의 업로드/실시간 시각화와 RF·Person-Feature 파이프라인을 함께 고도화했다. bbox 좌표계 정합성, 업로드 프리뷰 위 트래킹 리플레이, 2-slot 실시간 병렬 분석, HITL 재학습 완료 표시, XGBoost detection_frames 반환, RF 임계값 및 motion guard 개선, feature importance 기반 판단 근거 노출, 행동 분류 카드 제거, 모델 속도 힌트 및 파이프라인 설명 갱신을 한 번에 반영했다.

## 변경 파일 목록

### 프론트엔드
- `src/app/page.dashboard/view.pug`
	- 업로드 프리뷰 위 bbox 리플레이 오버레이/슬라이더/재생 버튼 추가
	- 행동 분류 카드/행동 모델 카드 제거
	- HITL 재학습 버튼 완료 상태 및 메시지 스타일 추가
	- 모델 선택 버튼에 속도 힌트 추가
- `src/app/page.dashboard/view.ts`
	- 실시간 분석 2-slot 병렬 큐 처리 추가
	- 업로드 프리뷰 비디오 기반 비동기 detection replay 렌더링 적용
	- HITL 재학습 완료 상태/메시지 타입/속도 힌트/파이프라인 설명 갱신
	- 파일 변경 시 리플레이/오버레이 상태 정리 로직 보강

### 백엔드
- `src/model/struct/video_analysis.py`
	- RF 파이프라인 `delta_y`를 하강 방향 기준으로 변경
	- aspect_ratio-only guard 및 강한 motion guard 억제 적용
	- threshold/risk level 조정 (`0.6`, high `0.75`)
	- feature importance 기반 분석 근거 카드 추가
	- person-feature `detection_frames` 매핑 추가
	- behavior_reason basis 카드 주입 제거
- `scripts/yolo_fall_runtime.py`
	- person-feature 추론 결과에 `detection_frames` 반환 추가
	- balanced 프로필 `vid_stride`를 3으로 상향해 추론 성능 개선

### 검증
- WIZ 프로젝트 빌드 정상 완료 (`clean: false`)
