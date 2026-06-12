# 자동 생성 단계 인라인 추가답변 입력 기능

- **ID**: 002
- **날짜**: 2026-04-21
- **유형**: 기능 추가

## 작업 요약
자동 생성 중 추가 정보 요청이 발생했을 때 검토 탭의 AI 채팅으로 이동하지 않고, 생성 화면 안에서 바로 질문을 선택해 답변을 입력·저장할 수 있도록 개선했다. 저장된 답변은 문서 설정의 참고 설명에 자동 합쳐져 이후 재생성 시 반영되도록 연결했다.

## 변경 파일 목록
### 백엔드
- `src/app/page.doc.write.item/api.py`
  - 추가 답변 저장 API `save_followup_answer()` 추가
  - 질문/답변을 `content_json.followup_answers`와 `settings_json.guide_notes`에 동기화

### 프론트엔드
- `src/app/page.doc.write.item/view.ts`
  - 생성 단계 추가 질문 선택, 답변 작성, 저장, 재생성 상태 관리 추가
- `src/app/page.doc.write.item/view.pug`
  - 생성 단계 내 인라인 답변 입력 패널 UI 추가
  - 답변 저장 여부 배지 및 저장 후 재생성 버튼 추가

## 검증
- 변경 파일 진단 오류 없음 확인
- WIZ 프로젝트 일반 빌드 성공 확인
