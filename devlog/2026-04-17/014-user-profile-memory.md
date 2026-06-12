# 사용자 프로필 메모리 시스템

- **ID**: 014
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
AI 설정 페이지에 "AI 기억 관리" 탭을 추가했다. AI가 문서 작성 대화에서 자동 학습한 사용자 정보(회사명, 직책, 부서 등)를 확인/편집/삭제할 수 있으며, 수동으로 정보를 추가할 수도 있다. AI Agent의 build_context()가 프로필 데이터를 자동 주입하여 다음 문서 작성에 활용한다.

## 변경 파일 목록

### App (page.ai.settings)
- `api.py` — get_profile, update_profile_key, delete_profile_key, clear_profile, save_profile_bulk 5개 엔드포인트 추가
- `view.ts` — 프로필 상태 변수(profileData, profileKeys, editing) 및 메서드(loadProfile, addProfileKey, startEditProfile, saveProfileKey, deleteProfileKey, clearAllProfile) 추가, 탭 구조(config/memory) 도입
- `view.pug` — 탭 네비게이션 추가, "AI 기억 관리" 탭 UI (설명 배너, 수동 추가 폼, 학습 정보 목록 + 편집/삭제)
