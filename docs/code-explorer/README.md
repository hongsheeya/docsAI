# FallAI 전체 코드 탐색 페이지

교수님께 코드 전체와 쉬운 설명을 함께 보여드리기 위한 문서입니다.

## 보는 방법

`docs/code-explorer/index.html`을 브라우저로 열면 됩니다.

- 왼쪽에는 FallAI 프로젝트의 소스 파일 목록이 나옵니다.
- 가운데/왼쪽 큰 영역에는 해당 파일의 원본 코드 전체가 나옵니다.
- 오른쪽에는 비전공자용 설명, 읽을 포인트, 주요 함수/클래스 위치가 나옵니다.

## 포함한 코드

직접 작성한 서비스 코드, 서버 코드, AI/학습 스크립트, 설정 파일을 포함했습니다.

## 제외한 항목

다음은 보안, 용량, 저작권, 검토 효율 때문에 제외했습니다.

- `node_modules`, `build`, `bundle`
- `storage`, `outputs`, `data`
- AI-Hub 원본 데이터
- 업로드 영상
- 학습된 모델 가중치
- 이미지, 폰트, 대용량 바이너리
- CKEditor 같은 외부 vendor 코드

## 다시 생성하는 방법

코드가 바뀐 뒤 아래 명령을 실행하면 `index.html`이 갱신됩니다.

```bash
python scripts/generate_code_explorer.py
```
