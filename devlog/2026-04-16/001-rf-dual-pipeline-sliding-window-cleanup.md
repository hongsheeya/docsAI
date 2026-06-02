# RF-Dual 파이프라인 정리 및 슬라이딩 윈도우 전환

- **ID**: 001
- **날짜**: 2026-04-16
- **유형**: 리팩토링

## 작업 요약
RF-Dual 운영 경로에서 `xg-fall` 노출을 제거하고, 업로드/실시간 공통 청크 정책을 Dense Sliding Window로 전환했다.
또한 `lie` 판정을 더 쉽게 허용하도록 posture heuristic을 완화해 앉기/눕기 경계가 덜 엄격하게 동작하도록 조정했다.

## 변경 파일 목록
### 백엔드
- `src/model/struct/video_analysis.py`: XG-Fall 노출 제거, prototype/runtime 설명 정리, 슬라이딩 청크 정책 반영, `lie` heuristic 완화, 재학습 체인에서 XG-Fall 제외

### 스크립트
- `scripts/bootstrap_models.py`: XG-Fall 디렉터리 생성 제거
- `scripts/direct_train.py`: XG-Fall 직접 학습 루틴 제거
