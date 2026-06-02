# 외부 행동 라벨 매핑 확장 및 클래스/행동 리포트 생성

- **ID**: 007
- **날짜**: 2026-04-21
- **유형**: 기능 추가

## 작업 요약
- 외부 person action 라벨의 직접 매핑을 `sit`, `walk`에서 `lie_on`, `stand_on`까지 확장하고, `hold`·`watch`·`no_interaction`·`straddle`에 대해 보수적 pose heuristic 기반 `stand`/`sit` 약지도 매핑을 추가했다.
- 확장 규칙을 반영해 XG-Posture를 재학습하고, 클래스별 precision/recall/f1/support와 행동별 매핑 현황을 모두 포함한 리포트 파일을 생성했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - 외부 action 직접 매핑 확장 (`lie_on`→`lie`, `stand_on`→`stand`)
  - weak action (`hold`, `watch`, `no_interaction`, `straddle`)의 pose heuristic 기반 `stand`/`sit` 매핑 추가
  - 외부 샘플 선택 시 클래스별 상한, 규칙별 confidence 정렬, rule/action/example 메타데이터 기록 추가
- `scripts/generate_xg_posture_report.py`
  - 클래스별 성능, 행동별 매핑 현황, 확장 전/후 비교를 Markdown/JSON 리포트로 생성하는 스크립트 추가
- `storage/training/fall-detection/xg-posture/training_summary.pre-expanded-mapping-2026-04-21.json`
  - 확장 전 성능/샘플 스냅샷 보존
- `storage/training/fall-detection/xg-posture/report/2026-04-21-xg-posture-class-action-report.md`
  - 최종 Markdown 리포트 생성
- `storage/training/fall-detection/xg-posture/report/2026-04-21-xg-posture-class-action-report.json`
  - 최종 JSON 리포트 생성
- `storage/training/fall-detection/xg-posture/training_summary.json`
  - 확장된 external mapping 메타데이터 반영
- `devlog.md`
  - 2026-04-21 작업 이력 007 추가
