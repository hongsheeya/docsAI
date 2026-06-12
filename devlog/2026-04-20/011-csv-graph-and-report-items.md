# CSV 기반 MATLAB 스타일 그래프 생성 및 레포트 항목 구조화 추가

- **ID**: 011
- **날짜**: 2026-04-20
- **유형**: 기능 추가

## 작업 요약
CSV 파일을 업로드하면 실험 데이터를 자동으로 읽어 MATLAB 스타일의 그래프 이미지로 생성하는 흐름을 추가했다. 또한 문서 주제와 분리된 `report_items` 구조를 저장·재사용할 수 있게 하여, "Trapezoidal trajectory를 PID 제어기에 입력한 실험 결과 레포트 작성해줘" 같은 범용 요청에도 동일한 레포트 항목 구조를 유지하도록 AI 프롬프트와 생성 흐름을 확장했다.

## 변경 파일 목록

### Backend — Model/Struct
- `src/model/struct/graph_gen.py`
  - CSV 업로드 저장, CSV 파싱, 숫자 열 자동 감지, 다중 시리즈 플롯 생성 추가
  - line/bar/scatter/pie 자동 선택과 MATLAB 스타일 색상 팔레트 적용
- `src/model/struct/ai_agent.py`
  - `build_context()`에 `report_items` 포함
  - 필드 생성/섹션 생성/채팅 프롬프트에 레포트 항목 구조 반영
  - 전체 레포트 요청 시 여러 `[SECTION_UPDATE:...]` 블록으로 응답하도록 채팅 규칙 보강

### Backend — App API
- `src/app/page.doc.write.item/api.py`
  - `save_settings()`에 `report_items` 저장 추가
  - `generate()`에서 비 템플릿 채움 모드 시 `report_items` 기반 섹션 구조 사용
  - `generate_chart()`에서 CSV 업로드 기반 그래프 생성 지원
  - `chat()`에서 CSV 첨부 시 자동 그래프 생성 후 이미지 자산으로 편입

### Frontend — 문서 작성 상세
- `src/app/page.doc.write.item/view.ts`
  - `report_items_text`, `chartCsvFile` 상태 추가
  - 설정 저장/불러오기와 CSV 그래프 생성 요청 로직 추가
- `src/app/page.doc.write.item/view.pug`
  - Step 1에 레포트 항목 구조 입력 UI 추가
  - 이미지/그래프 탭에 CSV 선택 UI 추가
  - AI 채팅 첨부 input이 CSV도 받도록 확장

## 검증
- 수정 파일 진단 오류 없음 확인
- 프로젝트 일반 빌드 성공 확인