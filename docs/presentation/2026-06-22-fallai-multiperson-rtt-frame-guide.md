# FallAI 인원수별 RTT와 프레임 처리 전략 발표자료

생성일: 2026-06-22

## 핵심 메시지

- 현재 낙상 판정 보증은 대표 1명 중심이며, 통제 환경에서는 2명까지 운영 가능하다고 설명한다.
- 2026-06-25 재측정 기준, 실시간 기본 설정에서 성능 저하 없음으로 말할 수 있는 선은 3명까지다.
- 4~5명은 RTT는 유지되지만 과검출이 33~38%로 늘어 “표시 가능, 판정 보수”로 설명한다.
- 브라우저 skeleton 및 서버 overlay는 5명 표시를 기준으로 하고, 20명은 처리량/정밀모드 한계 테스트다.
- 실시간 판정 입력은 4초 chunk, 2초 overlap, 서버 4fps, 약 16프레임을 기본으로 한다.
- 1~5명 합성 pose-only 벤치마크는 4fps 실시간 요구를 넘겼지만, 실제 성능 저하 여부는 정확도·ID 유지율·E2E p95까지 다시 봐야 한다.
- 다음 개발은 person별 timeseries, person_results[], chunk tail cache, 실제 다중 인원 RTT/F1 재검증이다.

## 산출물

- PPTX: `docs/presentation/2026-06-22-fallai-multiperson-rtt-frame-guide.pptx`
- 백업: `docs/presentation/archive/backup_20260622T065911Z`
