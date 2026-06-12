# 관리자 계정 생성 및 로그인 예외 처리

- **ID**: 001
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
admin 관리자 계정(ID: admin, PW: season123!@)을 자동 시드로 생성하고, 로그인 페이지에서 이메일 형식이 아닌 아이디도 허용하도록 수정. Outputly 브랜딩 적용.

## 변경 파일 목록

### Model
- `src/model/struct.py`: `_init_tables()`에 `_seed_admin()` 호출 추가, admin 계정 자동 생성 로직

### Page (page.access)
- `src/app/page.access/view.pug`: 입력 타입 email→text, 라벨 "아이디 / 이메일", Outputly 브랜딩 UI
- `src/app/page.access/view.ts`: 유효성 메시지 수정 ("아이디 또는 이메일을 입력해주세요.")
- `src/app/page.access/api.py`: 에러 메시지 수정 ("아이디와 비밀번호", "아이디 또는 비밀번호")
