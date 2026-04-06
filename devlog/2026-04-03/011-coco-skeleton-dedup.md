# COCO-17 스켈레톤 상수 중복 제거

- **ID**: 011
- **날짜**: 2026-04-03
- **유형**: 리팩토링

## 작업 요약
`drawBboxesOnCanvas()`과 detection replay 함수에서 동일하게 선언되던 `SKELETON_PAIRS`/`KP_COLORS` 및 `SKELETON_PAIRS_DET`/`KP_COLORS_DET`를 클래스 수준 `static readonly` 상수(`COCO_SKELETON_PAIRS`, `COCO_KP_COLORS`)로 통합하고, 기존 로컬 선언을 참조로 교체.

## 변경 파일 목록

### view.ts
- **추가**: `static readonly COCO_SKELETON_PAIRS` (16쌍) — 클래스 상단
- **추가**: `static readonly COCO_KP_COLORS` (17키포인트 색상 맵) — 클래스 상단
- **수정**: `drawBboxesOnCanvas()` 내 로컬 `SKELETON_PAIRS`/`KP_COLORS` → `Component.COCO_SKELETON_PAIRS`/`Component.COCO_KP_COLORS` 참조
- **수정**: detection replay 함수 내 `SKELETON_PAIRS_DET`/`KP_COLORS_DET` → 동일 상수 참조
