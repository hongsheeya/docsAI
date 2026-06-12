# 양식 메타데이터 구조 개편

- **ID**: 002
- **날짜**: 2026-04-20
- **유형**: 기능 추가

## 작업 요약
양식 설명을 프로젝트 전체 공통 설명으로 재정의하고, 문서 작성 화면의 설명은 문서별 참고 설명으로 분리했다. 템플릿 설명이 실제 AI/삽입 엔진 컨텍스트에 반영되도록 문서 인스턴스 생성 및 AI 컨텍스트 빌드 흐름을 수정했다.

## 변경 파일 목록
- src/app/page.doc.templates/view.pug — 설명 입력 라벨/도움말을 프로젝트 전체 설명 용도로 변경
- src/app/page.doc.write.item/view.pug — 문서별 참고 설명 라벨/안내 문구 분리
- src/app/page.doc.write/api.py — 템플릿 설명을 인스턴스 content_json에 포함
- src/model/struct/ai_agent.py — template_context를 프롬프트/컨텍스트에 포함
