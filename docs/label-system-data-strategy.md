# 3-Level 라벨 체계 + 데이터 수집 전략

## 1. 3-Level 라벨 체계

### Level 1 — 위험 이진 (fall / nonfall)
| 라벨 | 설명 | 디렉토리 |
|------|------|----------|
| `Y` (fall) | 낙상 | `intake/Y/` |
| `N` (nonfall) | 비낙상 | `intake/N/` |

### Level 2 — 자세 6-class
| 라벨 | 한글 | 설명 | 디렉토리 |
|------|------|------|----------|
| `stand` | 서기 | 직립 상태, 가만히 서 있음 | `intake/stand/` |
| `walk` | 걷기 | 전방 보행, 0.5-2Hz 주기 | `intake/walk/` |
| `run` | 뛰기 | 빠른 보행, >2Hz 주기 | `intake/run/` |
| `sit` | 앉기 | 의자/바닥 앉기, 주저앉기 | `intake/sit/` |
| `lie` | 눕기 | 침대/바닥 눕기, 옆눕기 | `intake/lie/` |
| `fall` | 낙상 | 급격한 하강 + 제어 불능 | `intake/fall/` |

### Level 3 — 옵션 태그 (피드백 메타데이터)
| 태그 | 설명 |
|------|------|
| `transition` | 자세 전이 중 (sit→stand 등) |
| `uncertain` | 대조군과 혼동 가능 (fast-sit vs fall 등) |
| `occluded` | 부분 가림 상태 |

## 2. sit/lie 세부 프로토콜

### sit 하위 유형
| 유형 | 설명 | 특징 |
|------|------|------|
| chair-sit | 의자 앉기 | 무릎 크게 굽힘, 몸통 기울기 낮음 |
| floor-sit | 바닥 앉기 | 크게 하강, floor_proximity 높음 |
| fast-sit | 빠르게 주저앉기 | down_speed 높음 — **fall과 혼동 대상** |

### lie 하위 유형
| 유형 | 설명 | 특징 |
|------|------|------|
| bed-lie | 침대 눕기 | 완만한 하강, 긴 전이 시간 |
| floor-lie | 바닥 눕기 | floor_proximity 높음, tilt 크게 변화 |
| side-lie | 옆으로 눕기 | horizontal spread 증가 |
| stretch-lie | 스트레칭/운동 | 주기적 동작, 빠른 회복 |

## 3. 데이터 수집 전략

### Phase 1: 기존 NonFall 재라벨링
- 대상: `intake/N/` 내 500건
- 방법: 수동 시청 → stand/walk/run/sit/lie/fall 6-class 재분류
- 결과 디렉토리: `intake/{posture_class}/`에 복사/이동

### Phase 2: 자체 촬영
- 조건 준수: 동일 카메라/해상도/거리/조명
- 시나리오별 최소 촬영 수: 각 유형별 50건+

### Phase 3: 공개 데이터셋 활용
- AI Hub 낙상사고 데이터
- 기타 행동인식 데이터셋

## 4. 클래스별 최소 목표

| 클래스 | 최소 목표 | 현재 | 우선순위 |
|--------|----------|------|----------|
| fall | 1000+ | 20 | ★★★ |
| stand | 300+ | 20 (N으로 라벨링된 것 포함) | ★★ |
| walk | 500+ | 0 | ★★★ |
| run | 300+ | 0 | ★★ |
| sit | 500+ | 0 | ★★★ |
| lie | 400+ | 0 | ★★★ |

## 5. Hard-case 세트

### sit-hard (fall과 혼동)
- 빠른 의자 앉기 (fast-sit)
- 푹 주저앉기 (collapse-sit)
- 화면밖 의자 앉기 (offscreen-chair)

### lie-hard (fall과 혼동)
- 침대 천천히 눕기 (slow-bed-lie)
- 바닥 내려가 눕기 (floor-descend-lie)
- 요가/스트레칭 (stretch-lie)

### fall-hard (비낙상과 혼동)
- 무릎 먼저 꿇고 넘어짐 (kneed-fall)
- 벽 짚다가 무너짐 (wall-collapse)
- 부분 가림 낙상 (occluded-fall)

> Hard-case 세트는 validation 세트에 반드시 별도 포함.

## 6. Intake 디렉토리 구조

```
storage/training/fall-detection/intake/
├── Y/              # Level 1: Fall (기존)
├── N/              # Level 1: NonFall (기존)
├── stand/          # Level 2: 서기
├── walk/           # Level 2: 걷기
├── run/            # Level 2: 뛰기
├── sit/            # Level 2: 앉기
├── lie/            # Level 2: 눕기
├── fall/           # Level 2: 낙상 (Y와 동일)
└── hard-case/      # 별도 보관
    ├── sit-hard/
    ├── lie-hard/
    └── fall-hard/
```

## 7. 라벨 전파 정책

| 모델 | 라벨 전파 방식 |
|------|-------------|
| XG-Fall | 레거시 참조용. 현재 운영 기본은 RF-Dual |
| XG-Posture | 영상 단위 라벨 전파 **금지** — 윈도우/interval 단위 라벨 필수 |

> XG-Posture는 영상 내에서 자세가 변화할 수 있으므로 (stand→sit 전이 등),
> 영상 단위 라벨을 모든 윈도우에 전파하면 노이즈 라벨이 됨.
> 현재는 peak window만 대표 라벨로 사용 (bootstrap 모드).

## 8. 검증 누수 방지 메모 (2026-04-27)

- posture 학습 스크립트의 교차검증은 이제 **window 단위 셔플 CV가 아니라 clip-grouped CV**를 사용해야 한다.
- 같은 영상에서 나온 여러 윈도우가 train/validation에 동시에 섞이면 성능이 과대평가될 수 있다.
- RF binary 재학습은 영상 단위 train/val 분할 후 특징 추출을 수행하므로 posture 스크립트보다 누수 위험이 낮다.
