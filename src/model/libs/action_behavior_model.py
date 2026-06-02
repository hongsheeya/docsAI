import json
import os
import datetime


SUMMARY_REL_PATH = os.path.join('storage', 'training', 'action-behavior', 'model', 'training_summary.json')
MODEL_REL_PATH = os.path.join('storage', 'training', 'action-behavior', 'model', 'behavior_model.json')

# ── FN-20260406-0002: 다중 자세 클래스 라벨 체계 ──

# 5-class 자세/행동 분류 정의.
# 낙상 최종 판정은 RF-Dual의 RF binary 레이어가 담당하고, 이 모듈은
# 비낙상 상태의 stand/walk/run/sit/lie 해석 메타데이터만 관리한다.
POSTURE_CLASSES = {
    'standing': {
        'code': 'standing',
        'label_ko': '서기',
        'label_en': 'Standing',
        'description': '두 발로 직립하여 서 있는 자세. 체중이 양 발에 분산.',
        'boundary_notes': '경미한 체중 이동은 standing으로 분류. 한 발짝 이상 이동하면 walking.',
        'binary_mapping': 'N',
        'pose_indicators': ['body_tilt_angle < 15°', 'knee_bend_angle > 160°', 'height_ratio > 0.8'],
    },
    'walking': {
        'code': 'walking',
        'label_ko': '걷기',
        'label_en': 'Walking',
        'description': '일정한 보폭으로 이동하는 자세. 양 발이 번갈아 지면에 접촉.',
        'boundary_notes': '서기 상태에서 한 발짝 이상 연속 이동 시 walking. 속도가 빨라지면 running.',
        'binary_mapping': 'N',
        'pose_indicators': ['center_descent_speed_mean < 0.1', 'horizontal movement present'],
    },
    'sitting': {
        'code': 'sitting',
        'label_ko': '앉기',
        'label_en': 'Sitting',
        'description': '의자, 바닥 등에 엉덩이를 대고 앉은 자세. 상체는 직립 또는 전경.',
        'boundary_notes': '무릎이 90° 이하로 굽히고 엉덩이가 지지면에 접촉. 등을 바닥에 대면 lying.',
        'binary_mapping': 'N',
        'pose_indicators': ['knee_bend_angle < 120°', 'body_tilt_angle < 30°', 'height_ratio 0.4~0.7'],
    },
    'running': {
        'code': 'running',
        'label_ko': '뛰기',
        'label_en': 'Running',
        'description': '보행보다 빠른 속도로 이동. 양 발이 동시에 지면에서 떨어지는 순간 존재.',
        'boundary_notes': 'walking과의 경계는 이동 속도 및 체공 여부. center_x 변화율이 walking의 2배 이상이면 running.',
        'binary_mapping': 'N',
        'pose_indicators': ['horizontal_spread_max elevated', 'center movement speed high'],
    },
    'lying': {
        'code': 'lying',
        'label_ko': '눕기',
        'label_en': 'Lying',
        'description': '바닥에 등, 배, 또는 옆을 대고 누운 자세. 의도적 휴식 포함.',
        'boundary_notes': '낙상과의 핵심 구분: 의도적(자발적) 전환이면 lying, 비자발적·급격한 전환이면 fall. '
                         'center_descent_speed_max < 0.2이고 점진적 전환이면 lying으로 분류.',
        'binary_mapping': 'N',
        'pose_indicators': ['body_tilt_angle > 60°', 'height_ratio < 0.3', 'horizontal_spread high'],
    },
    'fall': {
        'code': 'fall',
        'label_ko': '낙상',
        'label_en': 'Fall',
        'description': '비자발적으로 급격하게 바닥으로 넘어지는 동작. 신체 제어를 상실한 상태.',
        'boundary_notes': 'lying과의 핵심 구분: 급격한 수직 하강(center_descent_speed_max > 0.3), '
                         '비자발적 전환, body_tilt_angle의 급격한 변화(pose_change_rate_max > 0.5).',
        'binary_mapping': 'Y',
        'pose_indicators': ['center_descent_speed_max > 0.3', 'body_tilt_angle_max > 45° (rapid)', 'pose_change_rate_max > 0.5'],
    },
}

# 클래스 순서 (학습/추론 시 공통 사용)
MULTICLASS_ORDER = ['standing', 'walking', 'running', 'sitting', 'lying']
RUNTIME_CLASS_ORDER = ['stand', 'walk', 'run', 'sit', 'lie']

# 이진 → 다중 클래스 마이그레이션 매핑
BINARY_TO_MULTICLASS_MAPPING = {
    'Y': 'fall',       # 낙상 → fall 확정
    'N': 'unknown',    # 비낙상 → unknown (추후 세분화 필요)
    'fall': 'fall',
    'non-fall': 'unknown',
}

# 다중 클래스 → 이진 역매핑 (하위 호환)
MULTICLASS_TO_BINARY_MAPPING = {
    'standing': 'N',
    'walking': 'N',
    'sitting': 'N',
    'running': 'N',
    'lying': 'N',
    'fall': 'Y',
    'unknown': 'N',
}


def get_posture_class_info(code):
    """자세 클래스 코드로 상세 정보 반환."""
    return POSTURE_CLASSES.get(code)


def get_all_posture_classes():
    """전체 자세 클래스 옵션 목록 반환 (프론트엔드 드롭다운/버튼 그룹용)."""
    return [
        {
            'code': cls['code'],
            'label_ko': cls['label_ko'],
            'label_en': cls['label_en'],
            'description': cls['description'],
            'binary_mapping': cls['binary_mapping'],
        }
        for cls in [POSTURE_CLASSES[k] for k in MULTICLASS_ORDER]
    ]


def migrate_binary_label(binary_label):
    """이진 라벨(Y/N)을 다중 클래스 라벨로 변환."""
    return BINARY_TO_MULTICLASS_MAPPING.get(str(binary_label).strip().upper(), 'unknown')


def to_binary_label(multiclass_label):
    """다중 클래스 라벨을 이진 라벨(Y/N)로 역변환 (하위 호환)."""
    return MULTICLASS_TO_BINARY_MAPPING.get(str(multiclass_label).strip().lower(), 'N')


DEFAULT_SUMMARY = {
    'created_at': '',
    'model_type': 'behavior-posture-5class',
    'ready_by_rules': False,
    'ready': False,
    'dataset': {
        'sample_count': 0,
        'train_count': 0,
        'validation_count': 0,
        'class_distribution': {code: 0 for code in RUNTIME_CLASS_ORDER},
        'train_ratio': 0.7,
        'validation_ratio': 0.3,
        'split_strategy': 'runtime-feature-rules',
        'label_note': '행동분류는 stand/walk/run/sit/lie 5-class XG-Posture 계열 모델로 학습 후 활성화합니다.',
    },
    'train_metrics': {
        'accuracy': 0.0,
        'macro_f1': 0.0,
        'per_class': {},
        'note': '실제 5-class 행동분류 모델 학습 전 대기 메타데이터입니다.',
    },
    'validation_metrics': {
        'accuracy': 0.0,
        'macro_f1': 0.0,
        'per_class': {},
        'note': 'AI-Hub 71461 행동분류 데이터 확보 후 실제 학습 모델로 교체 예정입니다.',
    },
    'class_order': RUNTIME_CLASS_ORDER,
    # FN-20260406-0002: 다중 클래스 확장 준비 필드
    'multiclass_order': MULTICLASS_ORDER,
    'multiclass_ready': False,
    'runtime_source': 'rf-dual xg-posture layer',
}


DEFAULT_MODEL = {
    'model': 'behavior-posture-pending-v1',
    'updated_at': '',
    'class_order': RUNTIME_CLASS_ORDER,
    'multiclass_order': MULTICLASS_ORDER,
    'multiclass_ready': False,
    'ready': False,
    'source': 'aihub-71461-pending',
    'thresholds': {
        'fall_confirm': 0.465,
    },
    'notes': [
        '낙상 최종 판정은 RF-Dual RF binary 레이어가 담당합니다.',
        '행동분류는 비낙상 구간에서 stand/walk/run/sit/lie 5-class를 제공합니다.',
        'AI-Hub 71461 데이터 학습 완료 후 multiclass_ready=True로 활성화합니다.',
    ],
}


def _path(project_root, rel_path):
    return os.path.join(project_root, rel_path)


def read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return path


def training_summary(project_root):
    data = read_json(_path(project_root, SUMMARY_REL_PATH), default=None)
    if data is not None:
        return data
    return dict(DEFAULT_SUMMARY)


def train_and_save(project_root, force_rebuild=False):
    summary = training_summary(project_root)
    created_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    summary['created_at'] = created_at
    summary['model_type'] = 'behavior-posture-5class'
    summary['ready_by_rules'] = False
    summary['ready'] = False
    write_json(_path(project_root, SUMMARY_REL_PATH), summary)
    model = dict(DEFAULT_MODEL)
    model['updated_at'] = created_at
    write_json(_path(project_root, MODEL_REL_PATH), model)
    return {
        'summary': summary,
        'model': model,
    }
