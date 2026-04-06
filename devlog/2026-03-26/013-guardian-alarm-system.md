# 낙상 응급 프로토콜 보호자 알람 기능 구현

- **ID**: 013
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
기존 `dispatch_risk_alerts()`가 알림 상태만 기록하고 실제 전송을 하지 않았던 구조를 개선하여, SMS/Push 게이트웨이로 실제 HTTP 전송하도록 구현. 다중 보호자 관리, 알람 이력 조회 기능 추가.

## 변경 파일 목록

### 백엔드 Model (src/model/struct/video_analysis.py)
- `import requests as _http` 추가 (optional import)
- `_default_alert_settings()`: `guardians: []` 필드 추가 (다중 보호자 리스트)
- `_public_alert_settings()`: guardians 목록 포함하여 반환
- `_send_sms()`: **신규** — SMS 게이트웨이 webhook으로 실제 HTTP POST 전송
- `_send_push()`: **신규** — Push 게이트웨이 webhook으로 실제 HTTP POST 전송
- `_dispatch_to_guardians()`: **신규** — 모든 활성 보호자에게 SMS/Push 일괄 전송, 결과 리스트 반환
- `alert_history()`: **신규** — 알람 이력 페이지네이션 조회 (alerts 디렉토리 JSON 파일 스캔)
- `save_guardians()`: **신규** — 다중 보호자 목록 저장
- `dispatch_risk_alerts()`: 개선 — 실제 `_dispatch_to_guardians()` 호출, 전송 결과를 JSON 이력에 기록
- `analyze_upload()`: 하드코딩된 보호자 정보 → `_load_alert_settings()`에서 동적 로드

### 백엔드 API (src/app/page.admin.analysis/api.py)
- `alert_history()`: **신규** — 알람 이력 조회 엔드포인트 (page, page_size 지원)
- `save_guardians()`: **신규** — 다중 보호자 저장 엔드포인트 (JSON 배열)

### 프론트엔드 (src/app/page.admin.analysis/)
- `view.ts`:
  - `guardians: any[]`, `alertHistory`, `alertHistoryLoading`, `alertHistoryPage` 변수 추가
  - `addGuardian()`, `removeGuardian()`, `saveGuardians()` — 다중 보호자 CRUD
  - `loadAlertHistory()` — 알람 이력 로드 (페이지네이션)
  - `riskBadgeClass()`, `guardianStatusLabel()` — 이력 표시용 헬퍼
  - `applyAlertSettings()`: guardians 리스트 바인딩 추가
  - `ngOnInit()`: `loadAlertHistory()` 자동 호출
- `view.pug`:
  - 보호자 설정: 단일 입력 → 다중 보호자 리스트 UI (추가/삭제/활성화 체크박스)
  - **알람 이력 섹션** 신규 추가: 위험 수준 배지, 전송 상태, 보호자별 SMS/Push 결과, 페이지네이션

## 아키텍처
```
낙상 감지 (analyze_upload)
    → dispatch_risk_alerts()
        → _load_alert_settings() — 보호자 목록 + 게이트웨이 설정 로드
        → _dispatch_to_guardians() — 모든 활성 보호자에게 전송
            → _send_sms() — webhook HTTP POST (solapi 등)
            → _send_push() — webhook HTTP POST (FCM 등)
        → JSON 이력 파일 저장 (dispatch_results 포함)
    → 프론트엔드 alert_workflow 반영 (팝업/메시지)

관리자 페이지
    → 다중 보호자 등록/수정/삭제
    → 게이트웨이(SMS/Push) 설정
    → 알람 이력 목록 조회
```
