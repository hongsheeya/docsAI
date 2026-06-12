# AI 채팅 UX 고도화

- **ID**: 010
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
문서 작성 상세 페이지(page.doc.write.item)의 AI 채팅 탭에 빠른 프롬프트, 섹션 컨텍스트 선택, 섹션별 채팅 맥락 기능을 추가하여 AI와의 대화 품질과 사용 편의성을 개선했다.

## 변경 파일 목록

### 프론트엔드 (page.doc.write.item)
- `view.ts`: quickPrompts 배열(5개 한국어 프리셋), chatContextSection/setChatContext/clearChatContext, sendChat에 promptText 파라미터 지원, useQuickPrompt 메서드 추가
- `view.pug`: 채팅 탭에 섹션 컨텍스트 배너, 섹션 선택 버튼 바, 빠른 프롬프트 버튼 행 UI 추가
