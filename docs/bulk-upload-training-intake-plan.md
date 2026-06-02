# Bulk Upload Training Intake Plan

작성일: 2026-06-01

## 현재 반영

업로드 모드에서 여러 영상 파일 또는 zip/tar 압축 파일을 한 번에 선택할 수 있게 했다.

- 분석은 첫 번째 영상 파일을 기준으로 실행한다.
- 학습 데이터 등록은 선택된 전체 파일을 순차 업로드한다.
- 압축 파일은 서버에서 내부 영상 파일만 골라 같은 라벨로 intake에 저장한다.
- 저장 위치는 기존 학습 intake 구조를 유지한다.
  - 낙상/비낙상: `storage/training/fall-detection/intake/Y`, `N`
  - 행동 라벨: `storage/training/fall-detection/intake/stand|walk|run|sit|lie|fall`

## 라벨이 붙은 데이터 일괄 처리

사용자가 여러 파일을 같은 라벨로 올리는 경우:

1. 업로드 모드에서 여러 영상 또는 압축 파일 선택
2. 낙상 라벨 Y/N 선택
3. 행동 라벨 stand/walk/run/sit/lie/fall 선택
4. 전체 선택 파일 학습 데이터로 등록
5. 등록된 intake를 기반으로 기존 RF/XGBoost/Posture 재학습 스크립트 실행

## 라벨이 섞인 데이터 일괄 처리 구상

라벨이 섞인 압축 파일을 한 번에 받을 경우에는 바로 학습하지 않고 자동 분류 큐를 둔다.

1. 원본 업로드
   - `unlabeled_batch/<batch_id>`에 원본을 보관
   - 파일명, 경로, 압축 내부 경로, 업로드 시각을 manifest로 저장

2. 자동 pre-label
   - 현재 운영 모델로 fall/non-fall, posture, facial state를 먼저 추론
   - confidence가 높은 항목은 `auto_accept_candidate`
   - confidence가 낮거나 fall/posture 판단이 충돌한 항목은 `review_required`

3. 사용자 검수
   - 관리자 화면에서 썸네일/스켈레톤/예측 라벨을 보고 라벨 확정
   - 확정 전에는 학습 데이터로 사용하지 않음

4. 학습 반영
   - 확정된 항목만 intake의 Y/N 및 posture class 디렉토리로 복사 저장
   - Group split이 깨지지 않도록 batch_id/original_video_id를 metadata에 유지

## 주의점

- 모델이 스스로 예측한 라벨을 검수 없이 곧바로 재학습하면 오분류가 증폭된다.
- 같은 영상에서 잘린 여러 청크가 train/validation에 섞이면 성능이 부풀려질 수 있으므로 batch_id, original_video_id 기반 Group split이 필요하다.
- 압축 파일이 매우 큰 경우 브라우저 업로드보다 서버 경로 등록 방식이 안정적이다.

## 다음 구현 후보

- 관리자용 `unlabeled batch` 목록
- 자동 pre-label 결과 테이블
- confidence threshold 기반 자동/검수 분리
- 확정 라벨만 intake로 승격하는 API
