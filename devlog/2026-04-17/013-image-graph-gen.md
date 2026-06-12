# 이미지 업로드 및 AI 그래프 생성

- **ID**: 013
- **날짜**: 2026-04-17
- **유형**: 기능 추가

## 작업 요약
문서 검토 단계에 이미지 업로드 및 AI 그래프 생성 기능을 추가했다. GraphGen Sub-Struct로 matplotlib 기반 차트 생성(bar/line/pie/scatter)과 이미지 파일 관리를 구현하고, 프론트엔드에 이미지/그래프 탭을 추가했다.

## 변경 파일 목록

### Model
- `src/model/struct/graph_gen.py` — GraphGen Sub-Struct 신규 생성 (upload_image, list_images, get_image_bytes, delete_image, generate_chart, ai_generate_chart)
- `src/model/struct.py` — _GraphGen 로드 및 graph_gen property 추가

### App (page.doc.write.item)
- `api.py` — upload_image, list_images, get_image, delete_image, generate_chart 5개 엔드포인트 추가
- `view.ts` — 이미지 업로드/삭제, AI 그래프 생성, 갤러리 표시 메서드 추가
- `view.pug` — 리뷰 패널에 "이미지/그래프" 탭 추가 (업로드, AI 프롬프트, 갤러리 그리드)
