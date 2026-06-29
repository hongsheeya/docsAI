# FallAI 서버 복구 가이드

이 문서는 다른 서버에서 FallAI 사이트를 다시 띄우기 위한 절차입니다. GitHub에는 코드와 문서를 올리고, 대용량 데이터와 모델 파일은 별도 백업에서 복구하는 구조를 기준으로 합니다.

## 1. 복구에 필요한 구성

| 구분 | 설명 |
| --- | --- |
| 소스 코드 | GitHub 저장소에서 clone |
| Python/Node 실행환경 | WIZ, Python, Node.js, npm |
| 대용량 데이터 | `storage/`, `outputs/`, `data/`, `datasets/` 백업 |
| 모델 파일 | `.pkl`, `.joblib`, `.pt`, `.onnx` 등 별도 백업 |
| 환경 설정 | `.env`, API 키, 외부 서비스 토큰은 GitHub가 아니라 별도 보관 |

## 2. GitHub에 올리는 것과 올리지 않는 것

GitHub에는 코드와 설명 문서를 올립니다.

- `src/`
- `scripts/`
- `docs/`
- `README.md`
- `manual.md`
- 설정 예시 파일

GitHub에 올리지 않는 것이 안전한 항목입니다.

- `storage/`
- `outputs/`
- `data/`
- `datasets/`
- 원본 영상
- 학습 데이터 압축 파일
- 학습된 대용량 모델
- `.env`
- API 키와 GitHub 토큰

현재 `.gitignore`도 이 기준으로 구성되어 있습니다.

## 3. 새 서버에서 코드 내려받기

```bash
git clone <FallAI 저장소 주소>
cd main
```

저장소 이름은 실제로 만든 GitHub 저장소 주소에 맞춰 바꿉니다.

## 4. Python/Node 의존성 설치

프로젝트는 WIZ 기반 Python + Angular 구조입니다. 서버마다 환경이 다를 수 있으므로 기존 서버의 conda/pip 목록을 같이 보관하는 것이 좋습니다.

기본 확인:

```bash
python --version
node --version
npm --version
```

Node 의존성:

```bash
npm install
```

WIZ/Angular 빌드 쪽 의존성은 기존 배포 방식에 맞춰 설치합니다.

## 5. 대용량 백업 복구

GitHub에서 코드만 받은 상태로는 학습 데이터와 기존 분석 결과가 없습니다. 아래 폴더는 백업에서 복사해야 합니다.

```text
storage/
outputs/
data/
datasets/
```

권장 백업 위치 예시:

```text
/opt/app/backups/fallai-storage/
/opt/app/backups/fallai-outputs/
/opt/app/backups/fallai-datasets/
```

복구 예시:

```bash
rsync -a /opt/app/backups/fallai-storage/ storage/
rsync -a /opt/app/backups/fallai-outputs/ outputs/
rsync -a /opt/app/backups/fallai-data/ data/
```

## 6. 영구 저장소 링크 확인

이 프로젝트는 실행 중 생성되는 파일이 많기 때문에 `storage`, `outputs`를 영구 저장소로 연결해 두는 것이 좋습니다.

이미 만들어 둔 스크립트:

```bash
bash scripts/ensure_persistent_runtime_links.sh
```

복구 후에는 아래 명령으로 실제 경로가 살아 있는지 확인합니다.

```bash
ls -lah storage outputs data
```

## 7. 서버 실행

현재 서버에서는 WIZ 런타임을 아래 방식으로 실행했습니다.

```bash
wiz run --bundle --host=0.0.0.0 --port=3000 --log=/tmp/wiz-run-bundle-current.log
```

서버에서 3000 포트가 열려 있으면 브라우저에서 접속합니다.

```text
http://서버주소:3000/
```

## 8. 백그라운드 학습/모니터링 재시작

표정 모델 학습과 병목 모니터링은 별도 프로세스로 돌립니다.

```bash
bash scripts/restart_aihub82_supervisor_detached.sh
```

상태 확인:

```bash
pgrep -af 'continuous_aihub82_training_supervisor|train_facial_emotion_aihub82|monitor_aihub82'
tail -80 outputs/continuous_training/aihub82_supervisor.log
```

## 9. 4카메라 시뮬레이션 재현

서버 성능 확인용 4카메라 synthetic simulation:

```bash
python scripts/simulate_four_camera_tracking.py --frames 32 --stride 4 --imgsz 320 --conf 0.15 --quality-threshold 0.18 --repeats 3 --tag 320
python scripts/simulate_four_camera_tracking.py --frames 32 --stride 4 --imgsz 640 --conf 0.15 --quality-threshold 0.18 --repeats 3 --tag 640
```

결과는 `outputs/performance/`에 저장됩니다.

## 10. 복구 후 확인 체크리스트

- `/` 메인 분석 화면이 열리는가?
- `/models` 모델 관리 화면이 열리는가?
- `/pipeline` 파이프라인 설명 화면이 열리는가?
- 영상 업로드 분석이 동작하는가?
- 웹캠 분석이 동작하는가?
- 모델 버전과 백그라운드 학습 상태가 표시되는가?
- `outputs/continuous_training/` 상태 파일이 갱신되는가?
- 4카메라 시뮬레이션이 실행되는가?

## 11. 문제가 생겼을 때 보는 파일

| 문제 | 확인 위치 |
| --- | --- |
| 서버가 안 뜸 | `/tmp/wiz-run-bundle-current.log` |
| 모델 목록 오류 | `src/app/page.models/api.py`, `src/model/struct/video_analysis.py` |
| 영상 분석 오류 | `src/app/page.dashboard/api.py`, `src/model/struct/video_analysis.py` |
| 학습이 안 돔 | `outputs/continuous_training/`, `scripts/continuous_aihub82_training_supervisor.py` |
| 4카메라 테스트 오류 | `scripts/simulate_four_camera_tracking.py`, `outputs/performance/` |

## 12. 교수님께 공유할 때

교수님께는 GitHub 저장소와 함께 아래 문서를 같이 안내하면 됩니다.

- `README.md`
- `manual.md`
- `docs/professor-code-overview-20260629.md`
- `docs/server-restore-guide-20260629.md`

원본 데이터와 모델은 용량과 저작권/개인정보 문제가 있을 수 있으므로 GitHub가 아니라 별도 백업으로 관리하는 편이 안전합니다.
