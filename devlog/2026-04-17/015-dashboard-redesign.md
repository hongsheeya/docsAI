# 대시보드 Outputly 리디자인

- **ID**: 015
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
기존 블로그 스타일 대시보드를 Outputly AI 문서 작성 플랫폼에 맞게 전면 리디자인했다. 문서 통계 카드(전체/작성중/완료/이번주), 최근 문서 목록, 빠른 메뉴(문서 작성/양식 관리/AI 설정), AI 연결 상태 표시를 구현했다.

## 변경 파일 목록

### App (page.dashboard)
- `api.py` — overview 함수를 문서 통계(doc_instance) 기반으로 전면 교체 (total, in_progress, completed, this_week, templates, ai_active)
- `view.ts` — stats 타입을 object로 변경, statusLabel/statusClass 메서드 추가
- `view.pug` — Outputly 디자인 전면 교체 (통계 4카드, 최근 문서, 빠른 메뉴, AI 상태)
- `view.scss` — :host 블록 추가
