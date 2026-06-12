# 섹션 인라인 AI 수정 기능

- **ID**: 011
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
섹션 편집 탭에서 각 섹션에 인라인 AI 수정 요청 기능을 추가했다. 사용자가 섹션별로 수정 지시사항을 입력하면 AI가 해당 섹션을 지시에 따라 재작성한다.

## 변경 파일 목록

### 프론트엔드 (page.doc.write.item)
- `view.ts`: inlineEditSectionId/Instruction/Loading 상태, showInlineEdit/cancelInlineEdit/submitInlineEdit 메서드 추가, regenerate_section API에 instruction 파라미터 전달
- `view.pug`: 섹션 카드에 "AI 수정" 버튼, 인라인 수정 패널(지시사항 입력 + 제출/취소) UI 추가
