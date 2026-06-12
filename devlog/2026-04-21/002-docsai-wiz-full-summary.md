# DocsAI/WIZ 전체 개발 이력 및 주요 개선 요약 (2026-04-21)

---

## 1. 시스템/DB/기초 구조
- **2026-04-17**: 전체 DB 스키마 설계 및 생성 (문서, AI, 프로필, 채팅 6개 테이블)
  - `src/model/db/*.py`, `src/model/struct/doc.py`, `src/model/struct/ai.py`, `src/model/struct.py`
- **2026-04-17**: AI 설정 페이지(page.ai.settings) 및 CRUD/연결 테스트 구현
  - `src/app/page.ai.settings/*`
- **2026-04-17**: 문서 작성 메인(page.doc.write), 템플릿 관리(page.doc.templates), 상세 3-Step(page.doc.write.item) 등 전체 문서 작성 UI/로직 구축
  - `src/app/page.doc.write*`, `src/app/page.doc.templates*`

## 2. 파일 파싱/AI 엔진/기능 확장
- **2026-04-17**: 파일 파싱 엔진(file_parser Sub-Struct) — HWP/DOCX/PDF 텍스트/필드 자동 추출
  - `src/model/struct/file_parser.py`, `src/app/page.doc.write.item/api.py`
- **2026-04-17**: AI Agent 엔진(ai_agent Sub-Struct) — LLM 연동, 섹션 생성/채팅/스트리밍
  - `src/model/struct/ai_agent.py`, `src/app/page.doc.write.item/api.py`

## 3. 문서 생성/AI UX 고도화
- **2026-04-17~2026-04-20**: AI 채팅 UX, 인라인 AI 수정, PDF/DOCX 내보내기, 이미지/그래프 생성, 사용자 프로필 메모리, 대시보드 리뉴얼 등 다수 기능 추가
- **2026-04-20**: AI 커스텀 인스트럭션 시스템(DB/CRUD/프리셋/문서별 선택) 구현
  - `src/model/db/ai_instruction.py`, `src/model/struct/ai.py`, `src/model/struct/ai_agent.py`, `src/app/page.ai.settings/*`, `src/app/page.doc.write.item/*`
- **2026-04-20**: CSV 기반 MATLAB 스타일 그래프 생성, report_items 구조화, AI 프롬프트 반영
  - `src/model/struct/graph_gen.py`, `src/model/struct/ai_agent.py`, `src/app/page.doc.write.item/*`

## 4. 표/비정형 양식/자동 채움 고도화
- **2026-04-20**: 표 중심 양식 해석 강화, 추가 정보 질문 유도 흐름 구현
  - `src/model/struct/file_parser.py`, `src/model/struct/ai_agent.py`, `src/app/page.doc.write.item/api.py`, `src/app/page.doc.write.item/view.ts`
- **2026-04-21**: 표 기반 양식 채움 정밀화, 반복 행/예시 셀/샘플 텍스트 등 자동 채움 로직 강화, 참고자료 다중 업로드 확장
  - `src/model/struct/file_parser.py`, `src/app/page.doc.write.item/api.py`, `src/app/page.doc.write.item/view.ts`, `src/app/page.doc.write.item/view.pug`
- **2026-04-21**: 자동 생성 단계 인라인 추가답변 입력 기능, 저장 API 및 UI 구현
  - `src/app/page.doc.write.item/api.py`, `src/app/page.doc.write.item/view.ts`, `src/app/page.doc.write.item/view.pug`
- **2026-04-21**: 비정형 양식 이해 중심 프롬프트 강화, 원본 텍스트/섹션/참고자료 등 맥락 최대 반영, "비정형 양식 추론 프로토콜" 도입
  - `src/model/struct/ai_agent.py`, `src/model/struct/file_parser.py`, `src/app/page.doc.write.item/api.py`, `src/app/page.doc.write.item/view.ts`

## 5. 검증/문서화/향후 과제
- 모든 변경사항 진단/빌드/테스트 완료, 오류 없음 확인
- devlog.md 및 상세 devlog 파일에 작업 이력 기록
- 미해결: 실제 다양한 비정형 양식 추가 튜닝, followup answer 입력 시 생성 일시 중지 등 UX 개선 여지

---

### 참고: 상세 작업 이력(devlog)
- DB/AI/문서/프로필/채팅 스키마 설계 및 Struct 분리
- 파일 파싱 엔진(HWP/DOCX/PDF), AI Agent(LLM 연동/스트리밍)
- 문서 작성/템플릿/상세/통계/대시보드/AI 설정/커스텀 인스트럭션/그래프/이미지 등 전체 페이지 구축
- 표 기반 자동 채움, 반복 행/예시 셀/샘플 텍스트/참고자료 업로드/자동 분석/추가 정보 질문/인라인 답변/비정형 양식 추론 등 고도화
- 모든 변경 devlog.md 및 상세 devlog에 기록

2026-04-21 기준, DocsAI/WIZ는 표/비정형 양식 자동 채움, AI 프롬프트 강화, 참고자료 활용, 인라인 답변 등 실무 문서 자동화에 필요한 모든 핵심 기능을 갖추고 있으며, 지속적으로 고도화되고 있습니다.
