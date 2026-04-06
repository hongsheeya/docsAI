# 오버레이 6-class 행동분류 시각화 강화

- **ID**: 016
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
실시간 웹캠 오버레이 패널에 6-class 자세 확률 분포 바 차트를 추가했다. 현재 감지된 자세가 하이라이트되고, 각 자세별 아이콘·라벨·확률 바·퍼센트가 표시된다.

## 변경 파일 목록

### view.pug
- 오버레이 패널에 FN-0016 6-class 확률 분포 바 섹션 추가 (posture label과 basis text 사이)
- `hasPostureData()` 조건으로 posture_probs 데이터 있을 때만 표시
- `postureItems()` 반복으로 6개 바 렌더링 (icon, label, bar, %)
- 현재 감지 자세는 `bg-white/10` 배경 + 밝은 텍스트로 하이라이트
- 오버레이 최소/최대 너비를 260px/380px로 확장

### view.ts
- `postureItems()` 반환 타입에 `icon: string` 필드 추가
- `iconMap` 딕셔너리 추가 (🧍🚶🏃🪑🛌⚠️)
