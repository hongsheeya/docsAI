#!/usr/bin/env python3
import datetime
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path


PROJECT = Path(os.environ.get('PROJECT', '/opt/app/project/main'))
RUN_DIR = PROJECT / 'outputs' / 'continuous_training'
ARTIFACT_DIR = Path(os.environ.get(
    'FALLAI_OCC_ARTIFACT_DIR',
    '/opt/app/cache/fallai-training/continuous_training/xg-posture-occlusion',
))
STATUS_PATH = RUN_DIR / 'xg-posture_status.json'
HISTORY_PATH = ARTIFACT_DIR / 'targeted_occlusion_weak_pose_history.jsonl'
REPORT_MD_PATH = ARTIFACT_DIR / 'occlusion_weak_pose_report.md'
PID_PATH = ARTIFACT_DIR / 'targeted_occlusion_weak_pose.pid'
DEBUG_PATH = ARTIFACT_DIR / 'targeted_occlusion_debug.log'
TRAIN_REPORT_PATH = PROJECT / 'outputs' / 'model_optimization' / 'xg_posture_sequence_training_report.json'
TRAIN_SCRIPT = PROJECT / 'scripts' / 'retrain_xg_posture_sequence.py'
AUX_SUMMARY_PATH = Path('/opt/app/storage/training/fall-detection/xg-posture-occlusion-aux/training_summary.json')
PYTHON = os.environ.get('FALLAI_PYTHON', 'python3')
TARGET_F1 = float(os.environ.get('POSTURE_OCC_PRIORITY_TARGET', '0.95') or 0.95)
STRETCH_F1 = float(os.environ.get('POSTURE_OCC_STRETCH_TARGET', '0.95') or 0.95)
POLL_SEC = max(5, int(os.environ.get('POSTURE_OCC_STATUS_POLL_SEC', '12') or 12))


BASE_ENV = {
    'FALLAI_71461_DATASET_ROOTS': os.environ.get(
        'FALLAI_71461_DATASET_ROOTS',
        '/opt/app/tmp/datasets/action_behavior/aihub_71461',
    ),
    'POSTURE_INCLUDE_SYNTH_LOWER_OCCLUSION': '1',
    'POSTURE_INCLUDE_SYNTH_VERTICAL_OCCLUSION': '1',
    'POSTURE_INCLUDE_STATIC_WALK_MOTION_PRIOR': '1',
    'POSTURE_SAVE_OCCLUSION_AUX': '1',
    'POSTURE_OCC_AUX_MIN_SAVE_F1': '0.0',
    'POSTURE_DISABLE_ACTIVE_REPLACEMENT': '1',
    'POSTURE_ALLOW_MISSING_RUN': '1',
    'POSTURE_STATIC_RUN_LIMIT': '0',
    'POSTURE_AIHUB61_SEQ_RUN_LIMIT': '0',
    'POSTURE_AIHUB62_SEQ_RUN_LIMIT': '0',
    'POSTURE_AIHUB62_RAW_RUN_LIMIT': '0',
    'POSTURE_LOWER_OCCLUSION_RUN_LIMIT': '0',
    'POSTURE_SYNTH_SEQ_OCC_RUN_LIMIT': '0',
    'POSTURE_SYNTH_SEQ_VERTICAL_OCC_RUN_LIMIT': '0',
    'POSTURE_RF_INTAKE_PSEUDO_RUN_LIMIT': '0',
    'POSTURE_INCLUDE_TREE_ENSEMBLES': '1',
    'POSTURE_MODEL_FILTER': 'extra_trees,rf,xgb',
    'POSTURE_FEATURE_SET_FILTER': 'motion_breakthrough,occlusion_aware,upper_body_motion_focus,temporal_pose_core,sit_lie_geometry_focus,all_runtime_64',
}


CONFIGS = [
    {
        'name': 'lie_walk_balanced_fast',
        'description': 'lie/walk 약한 class 가중치 보정 + 기존 랜덤 하체/좌우 가림',
        'env': {
            'POSTURE_CLASS_WEIGHT_MULTIPLIERS': 'lie:1.25,walk:1.15',
            'POSTURE_STATIC_WALK_MOTION_PRIOR_LIMIT': '120',
            'POSTURE_MODEL_FILTER': 'extra_trees,rf',
            'POSTURE_FEATURE_SET_FILTER': 'motion_breakthrough,occlusion_aware,upper_body_motion_focus,all_runtime_64',
        },
    },
    {
        'name': 'lie_recall_boost',
        'description': 'lie recall 보강: lie 증강량과 lie rescue margin 확대',
        'env': {
            'POSTURE_CLASS_WEIGHT_MULTIPLIERS': 'lie:1.45,walk:1.10',
            'POSTURE_SYNTH_STATIC_OCC_LIE_LIMIT': '240',
            'POSTURE_SYNTH_STATIC_VERTICAL_OCC_LIE_LIMIT': '220',
            'POSTURE_POLICY_LIE_CLOSE_MARGIN': '0.22',
            'POSTURE_POLICY_LIE_PROB_MIN': '0.09',
            'POSTURE_POLICY_MAX_WALK_PROB': '0.28',
            'POSTURE_MODEL_FILTER': 'extra_trees,rf',
            'POSTURE_FEATURE_SET_FILTER': 'motion_breakthrough,sit_lie_geometry_focus,occlusion_aware,all_runtime_64',
        },
    },
    {
        'name': 'walk_motion_prior_boost',
        'description': 'walk 15건 한계를 motion-prior/가림 증강으로 보정',
        'env': {
            'POSTURE_CLASS_WEIGHT_MULTIPLIERS': 'walk:1.35,lie:1.20',
            'POSTURE_STATIC_WALK_MOTION_PRIOR_LIMIT': '180',
            'POSTURE_SYNTH_STATIC_OCC_WALK_LIMIT': '220',
            'POSTURE_SYNTH_STATIC_VERTICAL_OCC_WALK_LIMIT': '220',
            'POSTURE_POLICY_MAX_WALK_PROB': '0.30',
            'POSTURE_MODEL_FILTER': 'extra_trees,rf',
            'POSTURE_FEATURE_SET_FILTER': 'motion_breakthrough,upper_body_motion_focus,temporal_pose_core,occlusion_aware,all_runtime_64',
        },
    },
    {
        'name': 'xgb_margin_check',
        'description': 'tree ensemble 후보가 막히는 경우 XGB 얕은 모델로 margin 확인',
        'env': {
            'POSTURE_CLASS_WEIGHT_MULTIPLIERS': 'lie:1.30,walk:1.20',
            'POSTURE_STATIC_WALK_MOTION_PRIOR_LIMIT': '150',
            'POSTURE_POLICY_LIE_CLOSE_MARGIN': '0.20',
            'POSTURE_POLICY_LIE_PROB_MIN': '0.10',
            'POSTURE_MODEL_FILTER': 'xgb',
            'POSTURE_FEATURE_SET_FILTER': 'motion_breakthrough,occlusion_aware,sit_lie_geometry_focus,all_runtime_64',
        },
    },
]


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def debug_log(message):
    try:
        DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_PATH.open('a', encoding='utf-8') as file:
            file.write(f'[{now()}] {message}\n')
    except Exception:
        pass


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default if default is not None else {}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    tmp_path = path.with_name(f'.{path.name}.tmp')
    try:
        tmp_path.write_text(payload, encoding='utf-8')
        os.replace(tmp_path, path)
    except OSError:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        fallback = ARTIFACT_DIR / f'{path.name}.last_failed_write.json'
        fallback.parent.mkdir(parents=True, exist_ok=True)
        try:
            fallback.write_text(payload, encoding='utf-8')
        except Exception:
            pass


def latest_log_line(path):
    try:
        lines = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    except Exception:
        return ''
    for line in reversed(lines[-120:]):
        line = line.strip()
        if line:
            return line[-600:]
    return ''


def read_history(limit=80):
    rows = []
    try:
        lines = HISTORY_PATH.read_text(encoding='utf-8', errors='replace').splitlines()
    except Exception:
        return rows
    for line in lines[-limit:]:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def append_history(item):
    payload = json.dumps(item, ensure_ascii=False) + '\n'
    for path in (HISTORY_PATH, RUN_DIR / 'targeted_occlusion_weak_pose_history.fallback.jsonl'):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as file:
                file.write(payload)
            return True
        except OSError:
            continue
    return False


def active_aux_version_text():
    data = read_json(AUX_SUMMARY_PATH, {})
    return str(
        data.get('training_run_label')
        or data.get('model_version')
        or data.get('version_badge')
        or 'active'
    ).strip()


def cycle_version_text(cycle_number, experiment=''):
    try:
        cycle = int(cycle_number or 0)
    except Exception:
        cycle = 0
    suffix = str(experiment or '').strip()
    if cycle > 0 and suffix:
        return f'cycle #{cycle:04d} {suffix}'
    if cycle > 0:
        return f'cycle #{cycle:04d}'
    return suffix


def latest_cycle_number():
    highest = 0
    for item in read_history(limit=5000):
        try:
            highest = max(highest, int(item.get('cycle_number') or 0))
        except Exception:
            pass
    try:
        for path in ARTIFACT_DIR.glob('targeted_occlusion_cycle_*.log'):
            match = re.search(r'targeted_occlusion_cycle_0*([0-9]+)_', path.name)
            if match:
                highest = max(highest, int(match.group(1)))
    except Exception:
        pass
    try:
        status = read_json(STATUS_PATH, {})
        highest = max(highest, int(status.get('current_cycle') or 0))
    except Exception:
        pass
    return highest


def pid_state(pid):
    try:
        raw = Path(f'/proc/{int(pid)}/stat').read_text(encoding='utf-8', errors='replace')
        return raw.rsplit(')', 1)[1].strip().split()[0]
    except Exception:
        return ''


def pid_is_running(pid):
    try:
        pid = int(pid or 0)
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return pid_state(pid) != 'Z'
    except PermissionError:
        return True
    except Exception:
        return False


def estimate_eta_text(history, started_at, cycle_index, total_cycles):
    elapsed = max(0.0, time.time() - started_at)
    durations = [
        float(item.get('duration_sec') or 0.0)
        for item in history[-8:]
        if float(item.get('duration_sec') or 0.0) > 5
    ]
    if not durations:
        return f'학습 중 · 경과 {int(elapsed // 60)}분 {int(elapsed % 60)}초 · ETA 측정 중'
    avg_duration = sum(durations) / len(durations)
    remain_current = max(0.0, avg_duration - elapsed)
    remain_cycle_count = max(0, int(total_cycles) - int(cycle_index) - 1)
    remain = remain_current + remain_cycle_count * avg_duration
    if remain < 60:
        eta = f'{round(remain)}초'
    elif remain < 3600:
        eta = f'{int(remain // 60)}분 {round(remain % 60)}초'
    else:
        eta = f'{int(remain // 3600)}시간 {int((remain % 3600) // 60)}분'
    return f'학습 중 · 현재 사이클 남은 예상 {eta}'


def current_aux_f1():
    data = read_json(AUX_SUMMARY_PATH, {})
    group_cv = data.get('group_cv') if isinstance(data.get('group_cv'), dict) else {}
    seq_cv = data.get('sequence_group_cv') if isinstance(data.get('sequence_group_cv'), dict) else {}
    try:
        group_f1 = float(group_cv.get('f1_macro') or data.get('f1_macro') or 0.0)
    except Exception:
        group_f1 = 0.0
    try:
        sequence_f1 = float(seq_cv.get('f1_macro') or 0.0)
    except Exception:
        sequence_f1 = 0.0
    return max(group_f1, sequence_f1)


def current_aux_result():
    data = read_json(AUX_SUMMARY_PATH, {})
    group_cv = data.get('group_cv') if isinstance(data.get('group_cv'), dict) else {}
    seq_cv = data.get('sequence_group_cv') if isinstance(data.get('sequence_group_cv'), dict) else {}
    return {
        'config': 'active_occlusion_aux',
        'candidate_macro_f1': float(group_cv.get('f1_macro') or data.get('f1_macro') or 0.0),
        'candidate_accuracy': float(group_cv.get('accuracy') or data.get('accuracy') or 0.0),
        'candidate_sequence_macro_f1': float(seq_cv.get('f1_macro') or 0.0),
        'candidate_sequence_accuracy': float(seq_cv.get('accuracy') or 0.0),
        'candidate_model': data.get('algorithm') or '',
        'candidate_feature_set': data.get('feature_set') or '',
        'candidate_class_recall': group_cv.get('class_recall') or {},
        'candidate_sequence_class_recall': seq_cv.get('class_recall') or {},
        'active_classes': data.get('active_classes') or data.get('classes') or [],
        'dropped_classes': data.get('dropped_classes') or [],
        'class_distribution': data.get('class_distribution') or {},
        'loaded_class_distribution': data.get('loaded_class_distribution') or {},
        'summary_path': str(AUX_SUMMARY_PATH),
        'saved': bool(data.get('ready')),
        'skip_reason': data.get('reason') or 'active occlusion auxiliary summary',
    }


def extract_result(config_name, rc, duration_sec):
    report = read_json(TRAIN_REPORT_PATH, {})
    best = report.get('best') if isinstance(report.get('best'), dict) else {}
    aux = report.get('occlusion_auxiliary') if isinstance(report.get('occlusion_auxiliary'), dict) else {}
    seq = best.get('sequence_group_cv') if isinstance(best.get('sequence_group_cv'), dict) else {}
    active_aux = current_aux_result()
    result = {
        'config': config_name,
        'rc': int(rc),
        'duration_sec': round(float(duration_sec), 1),
        'applied': bool(report.get('applied')),
        'candidate_macro_f1': float(best.get('f1_macro') or report.get('candidate_f1_macro') or 0.0),
        'candidate_accuracy': float(best.get('accuracy') or 0.0),
        'candidate_sequence_macro_f1': float(seq.get('f1_macro') or 0.0),
        'candidate_sequence_accuracy': float(seq.get('accuracy') or 0.0),
        'candidate_model': best.get('model') or '',
        'candidate_feature_set': best.get('feature_set') or '',
        'candidate_class_recall': best.get('class_recall') or {},
        'candidate_sequence_class_recall': seq.get('class_recall') or {},
        'existing_aux_f1_macro': float(aux.get('existing_aux_f1_macro') or current_aux_f1() or 0.0),
        'active_aux_f1_macro': active_aux['candidate_macro_f1'],
        'active_aux_sequence_f1_macro': active_aux['candidate_sequence_macro_f1'],
        'saved': bool(aux.get('saved', aux.get('ready', False))),
        'skip_reason': aux.get('reason') or report.get('reason') or '',
        'active_classes': report.get('active_classes') or best.get('active_classes') or [],
        'dropped_classes': report.get('dropped_classes') or best.get('dropped_classes') or [],
        'class_distribution': report.get('class_distribution') or {},
        'loaded_class_distribution': report.get('loaded_class_distribution') or {},
        'report_path': str(TRAIN_REPORT_PATH),
    }
    if active_aux['candidate_macro_f1'] > result['candidate_macro_f1']:
        result['active_aux_is_best'] = True
        result['active_aux_model'] = active_aux['candidate_model']
        result['active_aux_feature_set'] = active_aux['candidate_feature_set']
    return result


def best_seen(history):
    best = {
        'candidate_macro_f1': 0.0,
        'candidate_sequence_macro_f1': 0.0,
        'config': '',
    }
    for item in history:
        for metric in ('candidate_macro_f1', 'candidate_sequence_macro_f1'):
            if float(item.get(metric) or 0.0) > float(best.get(metric) or 0.0):
                best = dict(item)
                break
    active_aux = current_aux_result()
    active_aux_score = max(
        float(active_aux.get('candidate_macro_f1') or 0.0),
        float(active_aux.get('candidate_sequence_macro_f1') or 0.0),
    )
    best_score = max(
        float(best.get('candidate_macro_f1') or 0.0),
        float(best.get('candidate_sequence_macro_f1') or 0.0),
    )
    if active_aux_score > best_score:
        best = active_aux
    return best


def write_status(stage, eta_text, message, latest_log='', extra=None):
    debug_log(f'write_status begin stage={stage}')
    data = read_json(STATUS_PATH, {'ok': True})
    data.update({
        'ok': True,
        'name': 'xg-posture',
        'label': 'XG-Posture/가림 보조 반복 학습',
        'stage': stage,
        'status': stage,
        'updated_at': now(),
        'eta_text': eta_text,
        'message': message,
        'latest_log': latest_log or data.get('latest_log') or '',
        'target_macro_f1': TARGET_F1,
        'stretch_macro_f1': STRETCH_F1,
        'occlusion_priority_target_macro_f1': TARGET_F1,
        'priority': 'visible-occlusion-weak-pose-loop',
        'supervisor_pid': os.getpid(),
        'active_aux_f1_macro': current_aux_f1(),
        'artifact_dir': str(ARTIFACT_DIR),
        'status_contract': 'Every background training cycle must update this file so the dashboard can display it.',
    })
    bottleneck = data.get('bottleneck') if isinstance(data.get('bottleneck'), dict) else {}
    bottleneck.update({
        'ready': True,
        'occlusion_source_ready': True,
        'message': '71461 라벨 zip 추출 완료. 병목은 데이터 유실이 아니라 lie/walk 성능과 실제 자세 라벨 부족입니다.',
    })
    data['bottleneck'] = bottleneck
    if extra:
        data.update(extra)
    active_version = active_aux_version_text()
    candidate_version = cycle_version_text(data.get('current_cycle'), data.get('experiment'))
    if active_version:
        data['active_version_text'] = active_version
    if stage == 'completed':
        candidate_version = ''
        data['candidate_version_text'] = ''
    elif candidate_version:
        data['candidate_version_text'] = candidate_version
    version_bits = []
    if candidate_version and stage != 'completed':
        version_bits.append('진행 ' + candidate_version)
    if active_version:
        version_bits.append('active ' + active_version)
    if version_bits:
        data['training_version_text'] = ' · '.join(version_bits)
    last_result = data.get('last_training_result') if isinstance(data.get('last_training_result'), dict) else {}
    if last_result:
        data['candidate_macro_f1'] = float(last_result.get('candidate_macro_f1') or 0.0)
        data['candidate_sequence_macro_f1'] = float(last_result.get('candidate_sequence_macro_f1') or 0.0)
        data['candidate_saved'] = bool(last_result.get('saved'))
        if last_result.get('skip_reason'):
            data['no_promotion_reason'] = str(last_result.get('skip_reason') or '')
    best_result = data.get('best_training_result') if isinstance(data.get('best_training_result'), dict) else {}
    if best_result:
        data['best_macro_f1'] = float(best_result.get('candidate_macro_f1') or 0.0)
        data['best_sequence_macro_f1'] = float(best_result.get('candidate_sequence_macro_f1') or 0.0)
    write_json(STATUS_PATH, data)
    debug_log(f'write_status end stage={stage}')


def write_report(history):
    latest = history[-1] if history else {}
    best = best_seen(history)
    recalls = latest.get('candidate_class_recall') if isinstance(latest.get('candidate_class_recall'), dict) else {}
    weak = sorted(recalls.items(), key=lambda item: float(item[1] or 0.0))[:3]
    lines = [
        '# 가림 보조 반복 학습 현황',
        '',
        f'- updated_at: {now()}',
        f'- target_macro_f1: {TARGET_F1:.3f}',
        f'- stretch_macro_f1: {STRETCH_F1:.3f}',
        f'- active_aux_f1: {current_aux_f1():.4f}',
        f'- best_seen: {best.get("config", "-")} · window F1 {float(best.get("candidate_macro_f1") or 0.0):.4f} · sequence F1 {float(best.get("candidate_sequence_macro_f1") or 0.0):.4f}',
        '',
        '## 최근 사이클',
        '',
        f'- config: {latest.get("config", "-")}',
        f'- candidate: {latest.get("candidate_model", "-")} / {latest.get("candidate_feature_set", "-")}',
        f'- window F1: {float(latest.get("candidate_macro_f1") or 0.0):.4f}',
        f'- sequence F1: {float(latest.get("candidate_sequence_macro_f1") or 0.0):.4f}',
        f'- saved: {latest.get("saved", False)}',
        f'- reason: {latest.get("skip_reason", "")}',
        '',
        '## 낮은 성능 자세',
        '',
    ]
    if weak:
        for label, value in weak:
            lines.append(f'- {label}: recall {float(value or 0.0):.4f}')
    else:
        lines.append('- 아직 분석 가능한 class recall이 없습니다.')
    lines.extend([
        '',
        '## 다음 조치',
        '',
        '- lie recall이 낮으면 lie 가중치, lie 하체/좌우 가림 증강량, lie rescue margin을 우선 조정합니다.',
        '- walk는 71461 실제 walk 라벨이 15건뿐이므로 motion-prior 증강으로 보완하되, 실제 연속 보행 자세 라벨이 들어오면 pseudo 성격을 줄입니다.',
        '- run은 현재 실제 자세/action 라벨 0건이라 active class에서 제외합니다. run 목표 복구에는 실제 run 자세 라벨이 필요합니다.',
    ])
    REPORT_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def cleanup_logs(keep=16):
    logs = sorted(ARTIFACT_DIR.glob('targeted_occlusion_cycle_*.log'), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in logs[keep:]:
        try:
            path.unlink()
        except Exception:
            pass


def run_cycle(config, cycle_number, cycle_index, total_cycles):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = ARTIFACT_DIR / f'targeted_occlusion_cycle_{cycle_number:04d}_{config["name"]}_{stamp}.log'
    env = os.environ.copy()
    env.update(BASE_ENV)
    env.update(config.get('env') or {})
    env['PYTHONUNBUFFERED'] = '1'
    started = time.time()
    history = read_history()
    write_status(
        'running',
        estimate_eta_text(history, started, cycle_index, total_cycles),
        f'{config["name"]} 학습 시작 · {config["description"]}',
        '학습 프로세스 시작',
        {
            'current_cycle': cycle_number,
            'cycle_index': cycle_index + 1,
            'cycle_total': total_cycles,
            'experiment': config['name'],
            'experiment_description': config['description'],
            'log_path': str(log_path),
            'pid': '',
        },
    )
    with log_path.open('w', encoding='utf-8') as log_file:
        process = subprocess.Popen(
            [PYTHON, str(TRAIN_SCRIPT)],
            cwd=str(PROJECT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        while True:
            rc = process.poll()
            line = latest_log_line(log_path)
            write_status(
                'running',
                estimate_eta_text(history, started, cycle_index, total_cycles),
                f'{config["name"]} 학습 중 · {config["description"]}',
                line or '학습 로그 수집 중',
                {
                    'current_cycle': cycle_number,
                    'cycle_index': cycle_index + 1,
                    'cycle_total': total_cycles,
                    'experiment': config['name'],
                    'experiment_description': config['description'],
                    'log_path': str(log_path),
                    'pid': process.pid,
                },
            )
            if rc is not None:
                break
            time.sleep(POLL_SEC)
    duration = time.time() - started
    result = extract_result(config['name'], rc, duration)
    result['cycle_number'] = cycle_number
    result['candidate_version_text'] = cycle_version_text(cycle_number, config['name'])
    result['finished_at'] = now()
    result['log_path'] = str(log_path)
    result['config_description'] = config['description']
    result['config_env'] = dict(config.get('env') or {})
    if not append_history(result):
        result['history_write_failed'] = True
        result['skip_reason'] = (result.get('skip_reason') or '') + ' · history write failed'
    history = read_history()
    write_report(history)
    best = best_seen(history)
    metric = max(float(best.get('candidate_macro_f1') or 0.0), current_aux_f1())
    if rc != 0:
        stage = 'running'
        eta = '실패 후 다음 설정으로 재시도'
        message = f'{config["name"]} 실패(rc={rc}). 멈추지 않고 다음 설정으로 넘어갑니다.'
    elif metric >= STRETCH_F1:
        stage = 'completed'
        eta = '최종 목표 달성'
        message = f'가림 보조 최종 목표 {STRETCH_F1:.2f} 달성. best F1 {metric:.4f}'
    elif metric >= TARGET_F1:
        stage = 'running'
        eta = f'1차 목표 달성 · 최종 {STRETCH_F1:.0%}까지 계속'
        message = f'가림 보조 1차 목표 {TARGET_F1:.2f}는 달성했지만 최종 목표까지 계속 반복 학습합니다.'
    else:
        stage = 'running'
        eta = '목표 미달 · 다음 설정 자동 진행'
        message = (
            f'후보 window F1 {result["candidate_macro_f1"]:.4f}, sequence F1 {result["candidate_sequence_macro_f1"]:.4f}. '
            'lie/walk 병목을 기준으로 다음 설정을 계속 학습합니다.'
        )
    write_status(
        stage,
        eta,
        message,
        latest_log_line(log_path),
        {
            'pid': '',
            'log_path': str(log_path),
            'last_training_result': result,
            'best_training_result': best,
            'history_path': str(HISTORY_PATH),
            'analysis_report_path': str(REPORT_MD_PATH),
        },
    )
    cleanup_logs()
    return result


def already_running():
    if not PID_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text(encoding='utf-8').strip() or '0')
    except Exception:
        return False
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        running = pid_is_running(pid)
    except Exception:
        running = False
    if not running:
        try:
            PID_PATH.unlink()
        except Exception:
            pass
    return running


def main():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    debug_log(f'supervisor start pid={os.getpid()}')
    if already_running():
        debug_log('already running detected; exiting')
        write_status(
            'running',
            '이미 실행 중',
            '가림 보조 반복 학습 관리자가 이미 실행 중입니다.',
            '중복 실행 방지',
        )
        return 0
    PID_PATH.write_text(str(os.getpid()) + '\n', encoding='utf-8')
    debug_log('pid file written')
    cycle_number = latest_cycle_number()
    debug_log(f'latest cycle number={cycle_number}')
    write_status(
        'running',
        '반복 학습 준비',
        '가림 보조 반복 학습 관리자를 시작했습니다. 모든 사이클은 백그라운드 학습 현황에 표시됩니다.',
        'supervisor started',
    )
    debug_log('initial status written')
    initial_best = best_seen(read_history())
    initial_metric = max(
        float(initial_best.get('candidate_macro_f1') or 0.0),
        float(initial_best.get('candidate_sequence_macro_f1') or 0.0),
        current_aux_f1(),
    )
    if initial_metric >= STRETCH_F1:
        write_status(
            'completed',
            '최종 목표 달성 · 타 모델 우선 학습으로 전환',
            f'가림 보조 sequence/window 기준 목표 {STRETCH_F1:.2f} 달성. 반복 학습을 종료하고 AI-Hub 82/173 등 다른 모델 학습을 우선합니다.',
            f'best window F1 {float(initial_best.get("candidate_macro_f1") or 0.0):.4f} · best sequence F1 {float(initial_best.get("candidate_sequence_macro_f1") or 0.0):.4f}',
            {
                'pid': '',
                'best_training_result': initial_best,
                'history_path': str(HISTORY_PATH),
                'analysis_report_path': str(REPORT_MD_PATH),
                'active_aux_f1_macro': float(current_aux_result().get('candidate_macro_f1') or 0.0),
                'best_sequence_macro_f1': float(initial_best.get('candidate_sequence_macro_f1') or 0.0),
                'priority': 'target-met-other-models-first',
            },
        )
        return 0
    try:
        while True:
            for idx, config in enumerate(CONFIGS):
                cycle_number += 1
                debug_log(f'run cycle begin cycle={cycle_number} config={config["name"]}')
                run_cycle(config, cycle_number, idx, len(CONFIGS))
                debug_log(f'run cycle end cycle={cycle_number} config={config["name"]}')
                history = read_history()
                best = best_seen(history)
                metric = max(float(best.get('candidate_macro_f1') or 0.0), current_aux_f1())
                if metric >= STRETCH_F1:
                    write_status(
                        'completed',
                        '최종 목표 달성 · 타 모델 우선 학습으로 전환',
                        f'가림 보조 최종 목표 {STRETCH_F1:.2f} 달성. 반복 학습을 종료하고 다른 모델 학습을 우선합니다.',
                        f'best window F1 {float(best.get("candidate_macro_f1") or 0.0):.4f} · best sequence F1 {float(best.get("candidate_sequence_macro_f1") or 0.0):.4f}',
                        {
                            'pid': '',
                            'best_training_result': best,
                            'history_path': str(HISTORY_PATH),
                            'analysis_report_path': str(REPORT_MD_PATH),
                            'active_aux_f1_macro': float(current_aux_result().get('candidate_macro_f1') or 0.0),
                            'best_sequence_macro_f1': float(best.get('candidate_sequence_macro_f1') or 0.0),
                            'priority': 'target-met-other-models-first',
                        },
                    )
                    return 0
                write_status(
                    'running',
                    '다음 실험 대기 20초',
                    '가림 보조 학습은 멈춘 것이 아니라 다음 설정으로 이어서 진행합니다.',
                    f'best window F1 {float(best.get("candidate_macro_f1") or 0.0):.4f} · active aux F1 {current_aux_f1():.4f}',
                    {
                        'pid': os.getpid(),
                        'best_training_result': best,
                        'history_path': str(HISTORY_PATH),
                        'analysis_report_path': str(REPORT_MD_PATH),
                    },
                )
                time.sleep(20)
    finally:
        debug_log('supervisor finally cleanup')
        try:
            PID_PATH.unlink()
        except Exception:
            pass


def _terminate(_signum, _frame):
    raise SystemExit(143)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _terminate)
    try:
        raise SystemExit(main())
    except BaseException as exc:
        debug_log(f'exit exception {type(exc).__name__}: {exc}')
        raise
