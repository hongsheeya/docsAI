# AI 커스텀 인스트럭션 시스템 구현

- **ID**: 008
- **날짜**: 2026-04-20
- **유형**: 기능 추가

## 작업 요약
AI 문서 생성 시 시스템 프롬프트가 하드코딩되어 있어 사용자가 어조/분량/형식을 커스터마이즈할 수 없던 문제를 해결.
DB 기반 인스트럭션 관리 시스템(CRUD + 토글)을 구현하고, AI 설정 페이지에 "인스트럭션" 탭, 문서 설정 Step 1에 인스트럭션 선택 UI를 추가하여 문서별/전역적으로 AI 지시사항을 적용할 수 있도록 함.

## 변경 파일 목록

### 신규 파일
- `src/model/db/ai_instruction.py` — DB 모델 스키마 (id, user_id, title, content, category, is_active, sort_order, created, updated)

### Backend — Model/Struct
- `src/model/struct.py` — _init_tables에 "ai_instruction" 추가, `_seed_instruction_presets()` 메서드 추가 (4개 시스템 프리셋: 전문적/공식 어조, 간결하게 요점만, 데이터/수치 중심, 창의적/자유로운 문체)
- `src/model/struct/ai.py` — `db_instruction` 초기화, 8개 인스트럭션 CRUD 메서드 추가 (create_instruction, list_instructions, list_all_instructions, get_instruction, update_instruction, delete_instruction, toggle_instruction, get_active_instructions)
- `src/model/struct/ai_agent.py` — `_build_instruction_text()` 메서드 추가, `build_context()`에 instruction_ids 반환 추가, `generate_field_values()`/`generate_section()` 시스템 프롬프트에 커스텀 인스트럭션 합성

### Frontend — AI 설정 페이지 (page.ai.settings)
- `api.py` — 5개 인스트럭션 API 추가 (list_instructions, create_instruction, update_instruction, delete_instruction, toggle_instruction)
- `view.ts` — 인스트럭션 탭 상태 변수, CRUD 메서드, 카테고리 필터, ngOnInit에 loadInstructions 추가
- `view.pug` — 3번째 탭 "인스트럭션" 추가 (설명, 생성/수정 폼, 카테고리별 필터, 목록 with 토글/수정/삭제)

### Frontend — 문서 작성 페이지 (page.doc.write.item)
- `api.py` — list_instructions 엔드포인트 추가, save_settings에 instruction_ids 저장 추가
- `view.ts` — instructions/selectedInstructionIds 상태 변수, loadInstructions/toggleInstructionSelect 메서드, saveSettings에 instruction_ids 포함
- `view.pug` — Step 1 설정에 "AI 인스트럭션" 선택 섹션 추가 (체크박스 리스트)
