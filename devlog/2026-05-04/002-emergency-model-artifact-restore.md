# 비상 모델 아티팩트 복구

- **ID**: 002
- **날짜**: 2026-05-04
- **유형**: 버그 수정

## 작업 요약
실제 문제를 UI가 아니라 저장소 유실로 재조사했다. `project/main/data` 심볼릭 링크 대상인 `/opt/app/_appdata/data` 자체가 사라져 있었고, `storage/training/fall-detection` 아래 RF/XG 모델 아티팩트도 전부 비어 있는 상태였다.

즉시 fallback 상태를 해제하기 위해 합성 feature 분포 기반 비상 복구 스크립트를 추가하고, RF 낙상 모델과 XG-Posture 번들을 재생성할 수 있도록 했다. 동시에 끊어진 data 루트와 업로드 디렉토리도 같이 복구했다.

## 원문 요청사항
```text
또 모델이 없어진거 같은데 찾아서 고쳐내

아니 복구 안되고 그대로잖아 제대로 찾아서 복구해놔
```

## 변경 파일 목록
- 스크립트
  - `scripts/emergency_restore_models.py`: 유실된 `_appdata/data` 디렉토리 구조를 재생성하고, 합성 feature 데이터로 RF/XG-Posture 비상 모델 아티팩트를 다시 만드는 복구 스크립트 추가
- Devlog
  - `devlog.md`: 작업 요약 행 추가
  - `devlog/2026-05-04/002-emergency-model-artifact-restore.md`: 상세 작업 기록 추가