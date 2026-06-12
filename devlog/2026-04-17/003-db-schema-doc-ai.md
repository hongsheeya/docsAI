# DB 스키마 생성 (문서·AI·프로필·채팅)

- **ID**: 003
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
Outputly 문서 작성 플랫폼의 전체 DB 스키마를 설계 및 생성. 문서 관련 3개 테이블(doc_template, doc_instance, doc_section), AI/프로필 관련 3개 테이블(ai_config, user_profile, ai_chat) 생성. Struct 패턴으로 비즈니스 로직 분리.

## 변경 파일 목록

### 신규 생성 — DB Model
- `src/model/db/doc_template.py` — 문서 양식 테이블 (title, file_path, file_type, fields_schema)
- `src/model/db/doc_instance.py` — 문서 인스턴스 테이블 (template_id, user_id, status, content_json, week_label)
- `src/model/db/doc_section.py` — 문서 섹션 테이블 (instance_id, section_key, content, sort_order, status)
- `src/model/db/ai_config.py` — AI 설정 테이블 (provider, model_name, api_key, endpoint, is_active)
- `src/model/db/user_profile.py` — 사용자 프로필 테이블 (user_id, profile_data, preferences, memo)
- `src/model/db/ai_chat.py` — AI 채팅 기록 테이블 (instance_id, section_id, role, content)

### 신규 생성 — Sub-Struct
- `src/model/struct/doc.py` — Doc Sub-Struct (Template/Instance/Section CRUD, 통계)
- `src/model/struct/ai.py` — AI Sub-Struct (Config CRUD, Chat 관리, Profile 관리)

### 수정
- `src/model/struct.py` — _init_tables()에 6개 테이블 등록, _Doc/_AI Sub-Struct 로드 및 프로퍼티 추가
