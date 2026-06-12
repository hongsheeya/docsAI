| 날짜 | ID | 작업 내용 | 상세 |
|------|-----|----------|------|
| 2026-04-22 | 001 | HWP→PDF 파싱 파이프라인 + 버그 수정 3건 (DOCX변환 실패, 채팅 첨부, 표 셀 오기입) | [상세](devlog/2026-04-22/001-hwp-pdf-parsing-pipeline.md) |
| 2026-04-22 | 002 | AI 표 이해도 대폭 개선 (camelot 설치 + 마크다운 표 + DOCX 병합 셀 감지 + regex 버그 수정) | [상세](devlog/2026-04-22/002-table-comprehension-improvements.md) |
| 2026-02-21 | 001 | 기존 인프라 page 앱 전체 삭제 및 일반 서비스 샘플 page 앱 생성 | [상세](devlog/2026-02-21/001-sample-pages-rebuild.md) |
| 2026-04-17 | 001 | 관리자 계정 생성 및 로그인 예외 처리 (admin/season123!@) | [상세](devlog/2026-04-17/001-admin-account-login.md) |
| 2026-04-17 | 002 | 사이드바 Outputly 브랜딩 UI 변경 (다크 테마) | [상세](devlog/2026-04-17/002-sidebar-outputly-branding.md) |
| 2026-04-17 | 003 | DB 스키마 생성 (문서·AI·프로필·채팅 6개 테이블 + Sub-Struct) | [상세](devlog/2026-04-17/003-db-schema-doc-ai.md) |
| 2026-04-17 | 004 | AI 설정 페이지 (page.ai.settings) — CRUD + 연결 테스트 | [상세](devlog/2026-04-17/004-ai-settings-page.md) |
| 2026-04-17 | 005 | 양식 관리 페이지 (page.doc.templates) — 파일 업로드/파싱 | [상세](devlog/2026-04-17/005-doc-templates-page.md) |
| 2026-04-17 | 006 | 문서 작성 메인 페이지 (page.doc.write) — 목록/통계/생성 | [상세](devlog/2026-04-17/006-doc-write-page.md) |
| 2026-04-17 | 007 | 문서 상세 3-Step 페이지 (page.doc.write.item) — 설정/AI생성/검토 | [상세](devlog/2026-04-17/007-doc-write-item-page.md) |
| 2026-04-17 | 008 | 파일 파싱 엔진 (file_parser Sub-Struct) — HWP/DOCX/PDF | [상세](devlog/2026-04-17/008-file-parser-engine.md) |
| 2026-04-17 | 009 | AI Agent 엔진 (ai_agent Sub-Struct) — LLM 연동/스트리밍 | [상세](devlog/2026-04-17/009-ai-agent-engine.md) |
| 2026-04-17 | 010 | AI 채팅 UX 고도화 — 빠른 프롬프트/섹션 컨텍스트 | [상세](devlog/2026-04-17/010-ai-chat-enhancement.md) |
| 2026-04-17 | 011 | 섹션 인라인 AI 수정 기능 | [상세](devlog/2026-04-17/011-section-inline-edit.md) |
| 2026-04-17 | 012 | PDF/DOCX 문서 내보내기 — ReportLab/WeasyPrint/python-docx | [상세](devlog/2026-04-17/012-doc-export-pdf-docx.md) |
| 2026-04-17 | 013 | 이미지 업로드 및 AI 그래프 생성 (matplotlib) | [상세](devlog/2026-04-17/013-image-graph-gen.md) |
| 2026-04-17 | 014 | 사용자 프로필 메모리 시스템 (AI 기억 관리) | [상세](devlog/2026-04-17/014-user-profile-memory.md) |
| 2026-04-17 | 015 | 대시보드 Outputly 디자인 리뉴얼 | [상세](devlog/2026-04-17/015-dashboard-redesign.md) |
| 2026-04-17 | 016 | 사이드바 템플릿 JIT 오류 및 manifest.json 오류 수정 | [상세](devlog/2026-04-17/016-sidebar-template-manifest-fix.md) |
| 2026-04-17 | 017 | 문서 작성 API 500 오류 수정 및 자유작성/스타일 참고 기능 추가 | [상세](devlog/2026-04-17/017-doc-write-api-fixes-and-style-reference.md) |
| 2026-04-20 | 001 | 양식 기반 작성 가능 범위 검토 및 DOCX/PDF/HWP capability 분석 | [상세](devlog/2026-04-20/001-template-capability-analysis.md) |
| 2026-04-20 | 002 | 양식 설명/문서별 설명 역할 분리 및 컨텍스트 흐름 개편 | [상세](devlog/2026-04-20/002-template-metadata-context-redesign.md) |
| 2026-04-20 | 003 | DOCX 원본 양식 유지형 필드 삽입 엔진 구현 | [상세](devlog/2026-04-20/003-template-preserving-fill-engine.md) |
| 2026-04-20 | 004 | 문서 목록 정렬·메타수정·삭제 관리 기능 추가 | [상세](devlog/2026-04-20/004-document-management-improvements.md) |
| 2026-04-20 | 005 | 문서 폴더 분류 기능 및 폴더 관리 UI 추가 | [상세](devlog/2026-04-20/005-folder-based-document-organization.md) |
| 2026-04-20 | 006 | PDF 다운로드 LibreOffice 기반 DOCX→PDF 변환 구현 | [상세](devlog/2026-04-20/006-pdf-libreoffice-conversion.md) |
| 2026-04-20 | 007 | AI 문서 생성 과정 전체 실시간 표시 (프롬프트/응답 로그) | [상세](devlog/2026-04-20/007-ai-generation-process-display.md) |
| 2026-04-20 | 008 | AI 커스텀 인스트럭션 시스템 구현 (DB/CRUD/프리셋/문서별 선택) | [상세](devlog/2026-04-20/008-custom-instruction-system.md) |
| 2026-04-20 | 009 | HWP 이미지 삽입 시 기존 내용 보존 및 API 배치 로직 개선 | [상세](devlog/2026-04-20/009-hwp-image-placement-preserve-content.md) |
| 2026-04-20 | 010 | HWP 시간 필드 파싱 및 세부활동 내용+이미지 병행 삽입 수정 | [상세](devlog/2026-04-20/010-hwp-time-and-detail-image-fill-fix.md) |
| 2026-04-20 | 011 | CSV 기반 MATLAB 스타일 그래프 생성 및 레포트 항목 구조화 추가 | [상세](devlog/2026-04-20/011-csv-graph-and-report-items.md) |
| 2026-04-20 | 012 | 표 중심 양식 해석 강화 및 추가 정보 질문 유도 흐름 구현 | [상세](devlog/2026-04-20/012-table-form-understanding-and-followup.md) |
| 2026-04-21 | 001 | 표 기반 양식 채움 정밀화 및 참고자료 다중 업로드 확장 | [상세](devlog/2026-04-21/001-table-fill-and-reference-upload.md) |
| 2026-04-21 | 002 | 자동 생성 단계 인라인 추가답변 입력 기능 | [상세](devlog/2026-04-21/002-inline-followup-answer-during-generation.md) |
| 2026-04-21 | 003 | 비정형 양식 이해 중심 프롬프트 강화 | [상세](devlog/2026-04-21/003-nonstandard-form-prompt-strengthening.md) |
