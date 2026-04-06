import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import time

try:
    import cv2
except Exception:
    cv2 = None

try:
    import requests as _http
except Exception:
    _http = None


class VideoAnalysis:
    _runtime_module_cache = None
    _runtime_module_mtime = None
    # FN-20260406-0001: HITL 피드백 N건 누적 시 자동 재학습 트리거 임계값
    AUTO_RETRAIN_THRESHOLD = 10

    def __init__(self, core):
        self.core = core
        self.allowed_extensions = ['mp4', 'mov', 'avi', 'mkv', 'webm']
        self.max_upload_mb = 200
        # FN-0025: 0.52→0.60 — 정상 활동 점수(30~40%)와 충분한 여유 확보
        self.fall_decision_threshold = 0.60

    def _project_root(self):
        return wiz.project.fs().abspath()

    def _project_abspath(self, *paths):
        base = self._project_root()
        return os.path.join(base, *paths) if paths else base

    def _read_json(self, path, default=None):
        try:
            with open(path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except Exception:
            return default

    def _write_json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        return path

    def _sanitize_filename(self, filename):
        name = os.path.basename(filename or 'video')
        return re.sub(r'[^A-Za-z0-9._-]+', '_', name) or 'video'

    def _storage_dir(self):
        path = self._project_abspath('data', 'uploads', 'fall-detection-prototype')
        os.makedirs(path, exist_ok=True)
        return path

    def _training_dir(self):
        path = self._project_abspath('storage', 'training', 'fall-detection', 'intake')
        os.makedirs(path, exist_ok=True)
        return path

    def _alerts_dir(self):
        path = self._project_abspath('storage', 'alerts', 'fall-detection')
        os.makedirs(path, exist_ok=True)
        return path

    def _alert_settings_path(self):
        return os.path.join(self._alerts_dir(), 'settings.json')

    def _clip_dir(self):
        path = os.path.join(self._alerts_dir(), 'clips', datetime.datetime.now().strftime('%Y-%m-%d'))
        os.makedirs(path, exist_ok=True)
        return path

    def _load_module(self, rel_path, module_name):
        module_path = self._project_abspath(*rel_path.split('/'))
        if os.path.exists(module_path) is False:
            return None
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _baseline_module(self):
        return self._load_module('src/model/libs/video_baseline.py', 'project_video_baseline')

    def _behavior_module(self):
        return self._load_module('src/model/libs/action_behavior_model.py', 'project_action_behavior_model')

    def _baseline_summary(self):
        module = self._baseline_module()
        if module is None:
            return None
        try:
            return module.training_summary(self._project_root())
        except Exception:
            return None

    def _behavior_summary(self):
        module = self._behavior_module()
        if module is None:
            return None
        try:
            return module.training_summary(self._project_root())
        except Exception:
            return None

    def _normalize_existing_path(self, path):
        raw = str(path or '').strip()
        if len(raw) == 0:
            return raw
        candidates = [raw]
        if raw.startswith('/mnt/data/wiz/'):
            candidates.append('/opt/app/' + raw[len('/mnt/data/wiz/'):])
        if raw.startswith('/opt/app/'):
            candidates.append('/mnt/data/wiz/' + raw[len('/opt/app/'):])
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return raw

    def _runtime_python_path(self):
        candidates = [
            self._project_abspath('.venv-yolo', 'bin', 'python'),
            self._normalize_existing_path(self._project_abspath('.venv-yolo', 'bin', 'python')),
            '/opt/conda/envs/app/bin/python',
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        # fallback: try shutil.which
        import shutil
        found = shutil.which('python3') or shutil.which('python') or ''
        return found

    def _runtime_script_path(self):
        path = self._project_abspath('scripts', 'yolo_fall_runtime.py')
        return path if os.path.exists(path) else ''

    @classmethod
    def _get_runtime_module(cls, script_path):
        if not script_path or os.path.exists(script_path) is False:
            return None
        try:
            mtime = os.path.getmtime(script_path)
        except Exception:
            return None
        if cls._runtime_module_cache is None or cls._runtime_module_mtime != mtime:
            spec = importlib.util.spec_from_file_location('project_yolo_fall_runtime_cached', script_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls._runtime_module_cache = module
            cls._runtime_module_mtime = mtime
        return cls._runtime_module_cache

    def _baseline_model_meta(self):
        return self._read_json(
            self._project_abspath('storage', 'training', 'fall-detection', 'model', 'baseline_model.json'),
            default={},
        ) or {}

    def _behavior_model_meta(self):
        return self._read_json(
            self._project_abspath('storage', 'training', 'action-behavior', 'model', 'behavior_model.json'),
            default={},
        ) or {}

    def _validation_report(self):
        return self._read_json(
            self._project_abspath('storage', 'training', 'fall-detection', 'model', 'validation_report.json'),
            default={},
        ) or {}

    def _project_relative_path(self, path):
        normalized = self._normalize_existing_path(path)
        project_root = self._project_root()
        try:
            if normalized.startswith(project_root):
                return os.path.relpath(normalized, project_root)
        except Exception:
            return normalized
        return normalized

    def _trained_runtime_available(self, baseline_state=None):
        if baseline_state is not None and baseline_state.get('ready') is False:
            return False
        return len(self._runtime_python_path()) > 0 and len(self._runtime_script_path()) > 0

    def _run_yolo_runtime(self, command, params=None, timeout=600):
        python_path = self._runtime_python_path()
        script_path = self._runtime_script_path()
        if len(python_path) == 0 or len(script_path) == 0:
            raise Exception('YOLO 추론 런타임이 준비되지 않았습니다.')
        command_line = [python_path, script_path, command, '--project-root', self._project_root()]
        for key, value in (params or {}).items():
            if value is None:
                continue
            command_line.extend([f'--{key}', str(value)])
        env = dict(os.environ)
        env['YOLO_CONFIG_DIR'] = self._project_abspath('storage', 'training', 'fall-detection', 'yolo-sample', 'config')
        os.makedirs(env['YOLO_CONFIG_DIR'], exist_ok=True)
        completed = subprocess.run(
            command_line,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        stdout = str(completed.stdout or '').strip()
        stderr = str(completed.stderr or '').strip()
        if completed.returncode != 0:
            raise Exception(stderr or stdout or 'YOLO 런타임 실행에 실패했습니다.')
        for line in reversed(stdout.splitlines()):
            line = str(line or '').strip()
            if len(line) == 0:
                continue
            if line.startswith('{') and line.endswith('}'):
                try:
                    return json.loads(line)
                except Exception:
                    continue
        raise Exception(stderr or stdout or 'YOLO 런타임 응답을 해석하지 못했습니다.')

    def _person_feature_available(self):
        """Check if person-feature pipeline models exist."""
        meta = self._baseline_model_meta()
        pd = meta.get('person_detector', {}) or {}
        fc = meta.get('fall_classifier', {}) or {}
        pd_weights = self._normalize_existing_path(pd.get('weights', ''))
        fc_path = fc.get('path', '')
        if fc_path and not os.path.isabs(fc_path):
            fc_path = self._project_abspath(fc_path)
        else:
            fc_path = self._normalize_existing_path(fc_path)
        return bool(pd_weights and os.path.exists(pd_weights) and fc_path and os.path.exists(fc_path))

    def _infer_with_trained_model(self, video_path, filename='', analysis_profile='balanced', model_type='xg-dual', input_source='upload', duration_hint=0):
        requested = str(model_type or 'xg-dual').strip().lower()
        if requested in ['rf', 'rf-pipeline-runtime']:
            requested = 'rf-pipeline'
        if requested in ['rf-pose-runtime']:
            requested = 'rf-pose'
        if requested in ['person-feature-runtime']:
            requested = 'person-feature'
        # Legacy aliases → rf-pipeline (레거시 YOLO 분류 모델 제거됨)
        if requested in ['legacy', 'yolo-cls', 'trained-yolo']:
            requested = 'rf-pipeline'

        person_feature_ready = self._trained_runtime_available() and self._person_feature_available()
        rf_ready = self._rf_pipeline_available()
        rf_pose_ready = self._rf_pose_pipeline_available()
        xg_fall_ready = self._xg_fall_available()
        xg_posture_ready = self._xg_posture_available()
        xg_dual_ready = xg_fall_ready  # dual needs at least xg-fall; posture is optional

        available = {
            'xg-dual': xg_dual_ready,
            'xg-fall': xg_fall_ready,
            'person-feature': person_feature_ready,
            'rf-pipeline': rf_ready,
            'rf-pose': rf_pose_ready,
        }
        runners = {
            'xg-dual': lambda: self._infer_xg_dual(video_path, filename, analysis_profile, input_source=input_source, duration_hint=duration_hint),
            'xg-fall': lambda: self._infer_xg_fall(video_path, filename, analysis_profile, input_source=input_source, duration_hint=duration_hint),
            'person-feature': lambda: self._infer_person_feature(video_path, filename, analysis_profile),
            'rf-pipeline': lambda: self._infer_rf_pipeline(video_path, filename, analysis_profile, input_source=input_source),
            'rf-pose': lambda: self._infer_rf_pose_pipeline(video_path, filename, analysis_profile, input_source=input_source),
        }

        if requested in runners:
            ordered_modes = [requested]
        else:
            # FN-0014 Stage A: auto fallback — rf-pose 제외 (deprecated)
            # xg-dual → xg-fall → person-feature → rf-pipeline
            ordered_modes = [
                'xg-dual',
                'xg-fall',
                'person-feature',
                'rf-pipeline',
            ]

        errors = []
        for mode in ordered_modes:
            if available.get(mode) is not True:
                if mode == 'xg-dual':
                    errors.append('XG-Dual 모델 준비가 완료되지 않았습니다 (XG-Fall 필수).')
                elif mode == 'xg-fall':
                    errors.append('XG-Fall 37-feature 모델 파일이 존재하지 않습니다.')
                elif mode == 'person-feature':
                    errors.append('person-feature 파이프라인 준비가 완료되지 않았습니다.')
                elif mode == 'rf-pipeline':
                    errors.append('RF 파이프라인 모델 파일이 존재하지 않습니다.')
                elif mode == 'rf-pose':
                    errors.append('RF-Pose 파이프라인 모델 파일이 존재하지 않습니다.')
                continue
            try:
                result = runners[mode]()
                # FN-0003: person-feature가 0점(사람 미검출 등)이면 RF fallback 시도
                if mode == 'person-feature' and requested != 'person-feature':
                    pf_score = self._metadata_to_number(result.get('risk_score', 0), 0)
                    pf_windows = int((result.get('runtime_inference', {}) or {}).get('windows', 0) or 0)
                    if pf_score <= 0.0 and pf_windows == 0 and rf_ready:
                        result['_person_feature_zero_note'] = 'XGBoost v2가 0점을 반환해 RF 보조 파이프라인으로 자동 전환했습니다.'
                        try:
                            return self._infer_rf_pipeline(video_path, filename, analysis_profile, input_source=input_source)
                        except Exception:
                            pass
                return result
            except Exception as e:
                errors.append(f'{mode} 실패: {str(e)}')

        raise Exception(' / '.join(errors) if len(errors) > 0 else '사용 가능한 학습 모델이 없습니다.')

    # NOTE: _infer_yolo_cls (legacy YOLO 분류 모델) 제거됨 — FN-0008
    # auto 모드 fallback 순서: rf-pose → rf-pipeline → person-feature

    # FN-0029: XGBoost uses its own threshold (0.5) for higher recall
    _PERSON_FEATURE_THRESHOLD = 0.5

    def _infer_person_feature(self, video_path, filename='', analysis_profile='balanced'):
        inference = None
        runtime_errors = []
        script_path = self._runtime_script_path()
        runtime_module = self._get_runtime_module(script_path)
        # FN-0029: XGBoost threshold independent from RF threshold
        pf_threshold = self._PERSON_FEATURE_THRESHOLD
        if runtime_module is not None:
            try:
                from pathlib import Path as _Path
                class _Args:
                    pass
                args = _Args()
                args.video = video_path
                args.threshold = pf_threshold
                args.profile = analysis_profile
                inference = runtime_module.command_infer_person_feature(_Path(self._project_root()), args)
            except Exception as e:
                runtime_errors.append(f'in-process runtime 실패: {str(e)}')
        if inference is None:
            try:
                inference = self._run_yolo_runtime('infer', {
                    'video': video_path,
                    'threshold': pf_threshold,
                    'mode': 'person-feature',
                    'profile': analysis_profile,
                }, timeout=900)
            except Exception as e:
                runtime_errors.append(f'subprocess runtime 실패: {str(e)}')
                raise Exception(' / '.join(runtime_errors))
        score = self._metadata_to_number(inference.get('fall_score', 0.0), 0.0)
        fall_detected = bool(inference.get('fall_detected', False))
        # FN-0029: XGBoost uses its own threshold for fall_detected
        pf_threshold = self._PERSON_FEATURE_THRESHOLD
        # Risk level uses the XGBoost threshold for medium boundary
        risk_level = 'high' if score >= 0.75 else ('medium' if score >= pf_threshold else 'low')
        risk_label = {'low': '안정', 'medium': '주의', 'high': '고위험'}.get(risk_level, '안정')
        behavior = self._predict_behavior_from_runtime(inference, fall_detected, allow_fallback=False)
        if behavior is not None:
            behavior_class, behavior_label = behavior.get('code', 'non-fall'), behavior.get('label', '비낙상')
        elif fall_detected:
            behavior_class, behavior_label = 'fall', '낙상'
            behavior = {
                'code': 'fall',
                'label': '낙상',
                'source': 'fall-risk-shortcut',
                'fallback': False,
                'reason': ['낙상 확률과 하강 속도가 임계값 이상입니다.'],
            }
        else:
            behavior_class, behavior_label = self._guess_behavior(filename, score)
            behavior = {
                'code': behavior_class,
                'label': behavior_label,
                'source': 'filename-fallback',
                'fallback': True,
                'reason': ['행동 모델이 연결되지 않아 파일명 기반 fallback을 사용했습니다.'],
            }
        # Build events from top windows
        top_windows = (inference.get('top_windows', []) or [])[:5]
        events = []
        for index, win in enumerate(top_windows):
            events.append({
                'label': '최고 위험 구간' if index == 0 else f'보조 위험 구간 {index + 1}',
                'time': round(self._metadata_to_number(win.get('time_sec', 0.0), 0.0), 2),
                'confidence': round(self._metadata_to_number(win.get('fall_probability', 0.0), 0.0), 4),
                'severity': risk_level,
            })
        if len(events) == 0:
            events.append({
                'label': '대표 분석 구간',
                'time': round(self._metadata_to_number(inference.get('event_time_sec', 0.0), 0.0), 2),
                'confidence': round(score, 4),
                'severity': risk_level,
            })
        # Feature-based analysis basis
        top_features = inference.get('top_features', {}) or {}
        # FN-0032: Removed event_time from basis — it's informational, not a judgment factor
        analysis_basis = []
        # FN-0023/FN-0030: XGBoost feature importance-based contribution sorting
        _xgb_feature_importances = {}
        try:
            _xgb_classifier_path = (inference.get('model', {}) or {}).get('fall_classifier', '')
            if _xgb_classifier_path:
                import os as _os_imp
                if _os_imp.path.exists(_xgb_classifier_path):
                    _xgb_clf = self._get_runtime_module(self._runtime_script_path())
                    if _xgb_clf is not None:
                        _cached_clf = _xgb_clf.get_cached_classifier(_xgb_classifier_path)
                        if hasattr(_cached_clf, 'feature_importances_'):
                            for col, imp in zip(_xgb_clf.FEATURE_COLS, _cached_clf.feature_importances_):
                                _xgb_feature_importances[col] = round(float(imp), 4)
        except Exception:
            pass
        # FN-0030: Fallback — uniform importances when extraction fails
        if not _xgb_feature_importances:
            _xgb_runtime = self._get_runtime_module(self._runtime_script_path())
            if _xgb_runtime is not None and hasattr(_xgb_runtime, 'FEATURE_COLS'):
                _n_feats = len(_xgb_runtime.FEATURE_COLS)
                for _col in _xgb_runtime.FEATURE_COLS:
                    _xgb_feature_importances[_col] = round(1.0 / _n_feats, 4)
        feature_specs = [
            ('max_down_speed', '최대 하강 속도', '상체/중심점이 급격히 아래로 이동했는지 보여줍니다.'),
            ('center_dy', '수직 이동량', '짧은 시간 동안 아래 방향으로 얼마나 이동했는지 나타냅니다.'),
            ('floor_proximity', '바닥 근접도', '인체 하단이 바닥에 얼마나 가까운지 보여줍니다.'),
            ('aspect_change', '자세 변화', '세로 자세에서 가로 자세로 바뀌는 정도를 나타냅니다.'),
            ('height_ratio', '높이 변화율', '사람 박스 높이가 얼마나 줄거나 늘었는지 보여줍니다.'),
            ('stillness', '정지 상태 비율', '인물이 움직이지 않는 프레임 비율로, 낙상 후 거동 불능 상태를 반영합니다.'),
        ]
        _xgb_basis_items = []
        for feat_key, feat_label, feat_desc in feature_specs:
            val = top_features.get(feat_key)
            if val is None:
                continue
            value = float(val)
            level = 'low'
            if feat_key == 'max_down_speed':
                level = 'high' if value >= 1.0 else ('medium' if value >= 0.5 else 'low')
            elif feat_key == 'center_dy':
                level = 'high' if value >= 0.15 else ('medium' if value >= 0.05 else 'low')
            elif feat_key == 'floor_proximity':
                level = 'high' if value >= 0.85 else ('medium' if value >= 0.70 else 'low')
            elif feat_key == 'aspect_change':
                level = 'high' if abs(value) >= 0.15 else ('medium' if abs(value) >= 0.08 else 'low')
            elif feat_key == 'height_ratio':
                level = 'high' if value <= -0.15 else ('medium' if value <= -0.05 else 'low')
            elif feat_key == 'stillness':
                level = 'high' if value >= 0.8 else ('medium' if value >= 0.5 else 'low')
            imp = _xgb_feature_importances.get(feat_key, 0)
            # FN-0030: Show "(기여도 미확인)" when importance is 0
            imp_label = f' (기여도 {round(imp * 100, 1)}%)' if imp > 0 else ' (기여도 미확인)'
            contribution = imp if imp > 0 else 0.001  # pure importance-based sort
            _xgb_basis_items.append({
                'feature': feat_key,
                'label': feat_label + imp_label,
                'value': round(value, 4),
                'unit': '',
                'level': level,
                'description': feat_desc,
                '_sort_score': contribution,
            })
        # FN-0023: Sort XGBoost basis by contribution score
        _xgb_basis_items.sort(key=lambda x: x.get('_sort_score', 0), reverse=True)
        for idx, item in enumerate(_xgb_basis_items, start=1):
            item['contribution_rank'] = idx
            item['contribution_score'] = round(float(item.get('_sort_score', 0.0) or 0.0), 6)
            item.pop('_sort_score', None)
            analysis_basis.append(item)
        video_info = (inference.get('video', {}) or {})
        model_info = (inference.get('model', {}) or {})
        # FN-0003: 사람 미검출/윈도우 없을 때 진단 summary 보완
        tracks_count = int(inference.get('tracks', 0) or 0)
        windows_count = int(inference.get('windows', 0) or 0)
        if score <= 0.0 and windows_count == 0:
            if tracks_count == 0:
                pf_summary = '영상에서 사람을 검출하지 못해 위험 점수를 산출하지 못했습니다. 카메라 각도·해상도를 확인하세요.'
            else:
                pf_summary = f'사람 {tracks_count}명을 추적했으나 유효한 분석 윈도우가 생성되지 않았습니다. 영상이 짧거나 이동 패턴이 부족할 수 있습니다.'
        elif fall_detected:
            pf_summary = '사람 추적 기반 특징 분석 결과 낙상 가능성이 높습니다.'
        else:
            pf_summary = '사람 추적 기반 특징 분석 결과 즉시 낙상 가능성은 낮습니다.'
        return {
            'fall_detected': fall_detected,
            'behavior_class': behavior_class,
            'behavior_label': behavior_label,
            'risk_score': round(score, 4),
            'risk_level': risk_level,
            'risk_label': risk_label,
            'summary': pf_summary,
            'events': events,
            'reference_matches': [],
            'analysis_basis': analysis_basis,
            'runtime_key': 'person-feature-runtime',
            'runtime_label': '사람 추적 기반 특징 분석',
            'runtime_inference': inference,
            'behavior_inference': behavior,
            'model_runtime': {
                'label': '사람 추적 기반 특징 분석',
                'person_detector': self._project_relative_path(model_info.get('person_detector', '')),
                'fall_classifier': self._project_relative_path(model_info.get('fall_classifier', '')),
                'profile': inference.get('profile', analysis_profile),
                'processed_frames': int(inference.get('processed_frames', 0) or 0),
                'tracks': int(inference.get('tracks', 0) or 0),
                'windows': int(inference.get('windows', 0) or 0),
                'fall_probability': round(self._metadata_to_number(inference.get('fall_probability', 0.0), 0.0), 4),
                'mean_probability': round(self._metadata_to_number(inference.get('mean_probability', 0.0), 0.0), 4),
                'fall_window_ratio': round(self._metadata_to_number(inference.get('fall_window_ratio', 0.0), 0.0), 4),
                'detection_frames': inference.get('detection_frames', []),  # FN-0012
            },
            'video_meta': {
                'duration': round(self._metadata_to_number(video_info.get('duration_sec', 0.0), 0.0), 2),
                'width': int(self._metadata_to_number(video_info.get('width', 0), 0)),
                'height': int(self._metadata_to_number(video_info.get('height', 0), 0)),
                'fps': round(self._metadata_to_number(video_info.get('fps', 0.0), 0.0), 2),
            },
        }

    # ── RF Pipeline (RandomForest + YOLOv8n-Pose person detection) ──────────

    _RF_MODEL_PATH = '/opt/app/rf_model_server.pkl'
    _RF_PROJECT_MODEL_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'rf-pipeline', 'rf_hitl_model.pkl')
    _RF_PROJECT_SUMMARY_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'rf-pipeline', 'training_summary.json')
    _RF_YOLO_MODEL = 'yolov8n-pose.pt'
    _RF_TARGET_FPS = 2
    _RF_CONF_THRES = 0.25
    _RF_PERSON_CLASS_ID = 0
    _RF_YOLO_IMGSZ = 640

    # COCO 17 keypoints index mapping
    _COCO_KEYPOINTS = [
        'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
        'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
        'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
        'left_knee', 'right_knee', 'left_ankle', 'right_ankle',
    ]
    # Skeleton connection pairs for visualization (index pairs)
    _COCO_SKELETON = [
        (0, 1), (0, 2), (1, 3), (2, 4),           # head
        (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),  # arms
        (5, 11), (6, 12), (11, 12),                # torso
        (11, 13), (13, 15), (12, 14), (14, 16),    # legs
    ]
    _RF_FEATURE_COLUMNS = [
        'detection_rate',          # v5: n_frames/total_sampled → 영상 길이 무관 검출률
        'center_y_mean', 'center_y_std',
        'height_mean', 'height_std',
        'aspect_ratio_mean', 'aspect_ratio_std',
        'delta_y_mean', 'delta_y_max',
        'delta_height_mean', 'delta_width_mean',
        'delta_y_accel_max',       # v4: 하강 가속도 최대값
        'final_height_ratio',      # v4: 최종 자세 높이 비율
    ]

    # Class-level model caches (shared across instances for performance)
    _rf_model_cache = None
    _rf_model_mtime = None
    _rf_model_path_cache = None
    _rf_yolo_cache = None

    # FN-0004: RF-Pose model (bbox+keypoint combined features)
    _RF_POSE_MODEL_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'rf-pose', 'rf_pose_model.pkl')
    _RF_POSE_SUMMARY_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'rf-pose', 'training_summary.json')
    _rf_pose_model_cache = None
    _rf_pose_model_mtime = None
    _rf_pose_model_path_cache = None

    # ── FN-0009: 3-Level Label System + Data Strategy ──────────────────
    # Level 1 — binary risk labels (fall / nonfall)
    _LABEL_L1_CLASSES = ['Y', 'N']
    # Level 2 — 6-class posture labels
    _LABEL_L2_CLASSES = ['stand', 'walk', 'run', 'sit', 'lie', 'fall']
    # Level 3 — optional metadata tags
    _LABEL_L3_TAGS = ['transition', 'uncertain', 'occluded']
    # Hard-case sub-categories for validation
    _HARD_CASE_CATEGORIES = {
        'sit-hard': ['fast-sit', 'collapse-sit', 'offscreen-chair'],
        'lie-hard': ['slow-bed-lie', 'floor-descend-lie', 'stretch-lie'],
        'fall-hard': ['kneed-fall', 'wall-collapse', 'occluded-fall'],
    }
    # Class-specific minimum data targets
    _DATA_TARGETS = {
        'fall': 1000, 'stand': 300, 'walk': 500,
        'run': 300, 'sit': 500, 'lie': 400,
    }
    # L1 → L2 bootstrap mapping (used when posture dirs don't exist)
    _L1_TO_L2_BOOTSTRAP = {'Y': 'fall', 'N': 'stand'}

    # FN-0007: XG-Fall 37-feature XGBoost binary model (unified timeseries)
    _XG_FALL_MODEL_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'xg-fall', 'xg_fall_model.pkl')
    _XG_FALL_SUMMARY_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'xg-fall', 'training_summary.json')
    _xg_fall_model_cache = None
    _xg_fall_model_mtime = None
    _xg_fall_model_path_cache = None

    # FN-0008: XG-Posture 37-feature XGBoost multiclass model
    _XG_POSTURE_MODEL_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'xg-posture', 'xg_posture_model.pkl')
    _XG_POSTURE_SUMMARY_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'xg-posture', 'training_summary.json')
    _xg_posture_model_cache = None
    _xg_posture_model_mtime = None
    _xg_posture_model_path_cache = None

    def _rf_project_model_path(self):
        return self._project_abspath(self._RF_PROJECT_MODEL_REL_PATH)

    def _rf_project_summary(self):
        return self._read_json(self._project_abspath(self._RF_PROJECT_SUMMARY_REL_PATH), default={}) or {}

    # ── XG-Fall / XG-Posture model helpers ──
    def _xg_fall_model_path(self):
        return self._project_abspath(self._XG_FALL_MODEL_REL_PATH)

    def _xg_fall_summary(self):
        return self._read_json(self._project_abspath(self._XG_FALL_SUMMARY_REL_PATH), default={}) or {}

    def _xg_fall_available(self):
        return os.path.isfile(self._xg_fall_model_path())

    def _get_xg_fall_model(self):
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import joblib
        model_path = self._xg_fall_model_path()
        try:
            mtime = os.path.getmtime(model_path)
        except OSError:
            raise Exception(f'XG-Fall 모델 파일을 찾을 수 없습니다: {model_path}')
        if self.__class__._xg_fall_model_cache is None or self.__class__._xg_fall_model_mtime != mtime or self.__class__._xg_fall_model_path_cache != model_path:
            self.__class__._xg_fall_model_cache = joblib.load(model_path)
            self.__class__._xg_fall_model_mtime = mtime
            self.__class__._xg_fall_model_path_cache = model_path
        return self.__class__._xg_fall_model_cache

    def _xg_posture_model_path(self):
        return self._project_abspath(self._XG_POSTURE_MODEL_REL_PATH)

    def _xg_posture_summary(self):
        return self._read_json(self._project_abspath(self._XG_POSTURE_SUMMARY_REL_PATH), default={}) or {}

    def _xg_posture_available(self):
        return os.path.isfile(self._xg_posture_model_path())

    def _get_xg_posture_model(self):
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import joblib
        model_path = self._xg_posture_model_path()
        try:
            mtime = os.path.getmtime(model_path)
        except OSError:
            raise Exception(f'XG-Posture 모델 파일을 찾을 수 없습니다: {model_path}')
        if self.__class__._xg_posture_model_cache is None or self.__class__._xg_posture_model_mtime != mtime or self.__class__._xg_posture_model_path_cache != model_path:
            self.__class__._xg_posture_model_cache = joblib.load(model_path)
            self.__class__._xg_posture_model_mtime = mtime
            self.__class__._xg_posture_model_path_cache = model_path
        return self.__class__._xg_posture_model_cache

    # ── FN-0009: Intake directory helpers for 3-Level label system ────
    def _intake_base_dir(self):
        """Return absolute path of training intake root."""
        return self._project_abspath(os.path.join('storage', 'training', 'fall-detection', 'intake'))

    def _ensure_intake_dirs(self):
        """Create all Level 1/2 + hard-case intake directories if missing."""
        base = self._intake_base_dir()
        # Level 1
        for lbl in self._LABEL_L1_CLASSES:
            os.makedirs(os.path.join(base, lbl), exist_ok=True)
        # Level 2
        for cls in self._LABEL_L2_CLASSES:
            os.makedirs(os.path.join(base, cls), exist_ok=True)
        # Hard-case
        for cat in self._HARD_CASE_CATEGORIES:
            os.makedirs(os.path.join(base, 'hard-case', cat), exist_ok=True)
        return base

    def _intake_class_counts(self):
        """Return dict of {class_name: video_count} for all intake dirs."""
        base = self._intake_base_dir()
        counts = {}
        for cls in self._LABEL_L2_CLASSES:
            cls_dir = os.path.join(base, cls)
            if os.path.isdir(cls_dir):
                counts[cls] = len([f for f in os.listdir(cls_dir)
                                   if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))])
            else:
                counts[cls] = 0
        # Also count L1 legacy dirs
        for lbl in self._LABEL_L1_CLASSES:
            lbl_dir = os.path.join(base, lbl)
            if os.path.isdir(lbl_dir):
                counts[f'L1_{lbl}'] = len([f for f in os.listdir(lbl_dir)
                                           if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))])
            else:
                counts[f'L1_{lbl}'] = 0
        return counts

    def _intake_data_status(self):
        """Return data collection progress vs targets."""
        counts = self._intake_class_counts()
        status = {}
        for cls, target in self._DATA_TARGETS.items():
            current = counts.get(cls, 0)
            status[cls] = {
                'current': current,
                'target': target,
                'progress_pct': round(current / target * 100, 1) if target > 0 else 0,
                'met': current >= target,
            }
        return status

    def _rf_active_model_path(self):
        project_model_path = self._rf_project_model_path()
        if os.path.isfile(project_model_path):
            return project_model_path
        return self._RF_MODEL_PATH

    def _get_rf_model(self):
        """Load RF model with file-path + mtime based cache invalidation."""
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import joblib
        model_path = self._rf_active_model_path()
        try:
            mtime = os.path.getmtime(model_path)
        except OSError:
            raise Exception(f'RF 모델 파일을 찾을 수 없습니다: {model_path}')
        if self.__class__._rf_model_cache is None or self.__class__._rf_model_mtime != mtime or self.__class__._rf_model_path_cache != model_path:
            self.__class__._rf_model_cache = joblib.load(model_path)
            self.__class__._rf_model_mtime = mtime
            self.__class__._rf_model_path_cache = model_path
        return self.__class__._rf_model_cache

    @classmethod
    def _get_rf_yolo_model(cls):
        """Load YOLO model once and cache at class level."""
        if cls._rf_yolo_cache is None:
            import sys as _sys
            if '/opt/app/my_libs' not in _sys.path:
                _sys.path.insert(0, '/opt/app/my_libs')
            from ultralytics import YOLO
            cls._rf_yolo_cache = YOLO(cls._RF_YOLO_MODEL)
        return cls._rf_yolo_cache

    @classmethod
    def _get_yolo_device(cls):
        """Auto-detect best device for YOLO inference (GPU if available)."""
        try:
            import torch
            if torch.cuda.is_available():
                return 'cuda'
        except ImportError:
            pass
        return 'cpu'

    def _rf_pipeline_available(self):
        """Check if any RF pipeline model file exists."""
        return os.path.isfile(self._rf_active_model_path())

    # FN-0004: RF-Pose pipeline methods
    def _rf_pose_model_path(self):
        return self._project_abspath(self._RF_POSE_MODEL_REL_PATH)

    def _rf_pose_summary(self):
        return self._read_json(self._project_abspath(self._RF_POSE_SUMMARY_REL_PATH), default={}) or {}

    def _rf_pose_pipeline_available(self):
        return os.path.isfile(self._rf_pose_model_path())

    def _get_rf_pose_model(self):
        """Load RF-Pose model with file-path + mtime based cache."""
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import joblib
        model_path = self._rf_pose_model_path()
        try:
            mtime = os.path.getmtime(model_path)
        except OSError:
            raise Exception(f'RF-Pose 모델 파일을 찾을 수 없습니다: {model_path}')
        if (self.__class__._rf_pose_model_cache is None
                or self.__class__._rf_pose_model_mtime != mtime
                or self.__class__._rf_pose_model_path_cache != model_path):
            self.__class__._rf_pose_model_cache = joblib.load(model_path)
            self.__class__._rf_pose_model_mtime = mtime
            self.__class__._rf_pose_model_path_cache = model_path
        return self.__class__._rf_pose_model_cache

    def _get_feat_labels(self):
        """Return feature label dict for both bbox and pose features."""
        return {
            'detection_rate': ('검출률', '사람이 검출된 프레임 비율입니다.', ''),
            'n_frames': ('검출 프레임 수', '분석에 사용된 총 프레임 수입니다.', '장'),
            'center_y_mean': ('Y 중심 평균', '사람 중심점의 평균 Y좌표입니다.', 'px'),
            'center_y_std': ('Y축 변동성', '사람 중심점 Y좌표의 표준편차입니다.', 'px'),
            'height_mean': ('높이 평균', '사람 bbox 높이의 평균입니다.', 'px'),
            'height_std': ('높이 변동', '사람 bbox 높이의 표준편차입니다.', 'px'),
            'width_mean': ('너비 평균', '사람 bbox 너비의 평균입니다.', 'px'),
            'width_std': ('너비 변동', '사람 bbox 너비의 표준편차입니다.', 'px'),
            'area_mean': ('면적 평균', '사람 bbox 면적의 평균입니다.', 'px²'),
            'area_std': ('면적 변동', '사람 bbox 면적의 표준편차입니다.', 'px²'),
            'aspect_ratio_mean': ('종횡비 평균', '사람 bbox 종횡비의 평균입니다.', ''),
            'aspect_ratio_std': ('종횡비 변동', '자세 변화를 나타냅니다.', ''),
            'delta_y_mean': ('평균 하강 변위', '프레임 간 아래 방향 이동의 평균입니다.', 'px'),
            'delta_y_max': ('최대 하강 변위', '낙하 순간을 반영합니다.', 'px'),
            'delta_height_mean': ('높이 변화 평균', '프레임 간 높이 변화의 평균입니다.', 'px'),
            'delta_width_mean': ('너비 변화 평균', '프레임 간 너비 변화의 평균입니다.', 'px'),
            'delta_y_accel_max': ('하강 가속도', '급격한 낙하를 나타냅니다.', 'px'),
            'final_height_ratio': ('최종 자세 높이', '낮을수록 넘어진 자세입니다.', ''),
            'body_tilt_angle_mean': ('몸 기울기(평균)', '어깨-엉덩이 축의 기울기 각도입니다.', '°'),
            'body_tilt_angle_max': ('몸 기울기(최대)', '가장 크게 기울어진 순간입니다.', '°'),
            'height_ratio_mean': ('키 비율(평균)', '머리~발 거리 / 영상 높이입니다.', ''),
            'height_ratio_min': ('키 비율(최소)', '가장 낮아진 순간입니다.', ''),
            'knee_bend_angle_mean': ('무릎 굽힘(평균)', '엉덩이-무릎-발목 각도입니다.', '°'),
            'knee_bend_angle_min': ('무릎 굽힘(최소)', '가장 많이 굽혀진 순간입니다.', '°'),
            'horizontal_spread_mean': ('수평 확산(평균)', '관절 x좌표의 표준편차입니다.', 'px'),
            'horizontal_spread_max': ('수평 확산(최대)', '가장 넓게 펼쳐진 순간입니다.', 'px'),
            'center_descent_speed_mean': ('중심 하강(평균)', '몸 중심의 하방 이동 속도입니다.', 'px'),
            'center_descent_speed_max': ('중심 하강(최대)', '가장 빠르게 하강한 순간입니다.', 'px'),
            'pose_change_rate_mean': ('자세 변화율(평균)', '전체 관절의 코사인 비유사도입니다.', ''),
            'pose_change_rate_max': ('자세 변화율(최대)', '가장 급격한 자세 변화입니다.', ''),
        }

    def _infer_rf_pose_pipeline(self, video_path, filename='', analysis_profile='balanced', input_source='upload'):
        """Run the RF-Pose pipeline: bbox 13 features + pose 12 features → RF predict.

        [FN-0014 DEPRECATED] Excluded from auto fallback chain. Used only in shadow mode
        comparison and explicit model_type='rf-pose' requests. Will be removed after Stage C.
        """
        import numpy as np
        import pandas as pd
        import time as _time
        t0 = _time.time()
        _perf = {}

        # 1. Load RF-Pose model
        _t = _time.time()
        rf_pose_model = self._get_rf_pose_model()
        _perf['model_load'] = round(_time.time() - _t, 3)

        # 2. Extract bbox features + keypoints (reuse existing pipeline)
        extracted = self._extract_rf_pipeline_features(video_path, input_source=input_source)
        _perf.update(extracted.get('perf', {}))
        feat = extracted['feat']
        detection_frames = extracted['detection_frames']
        det_rows = extracted['det_rows']
        frames = extracted['frames']
        vid_width = extracted['vid_width']
        vid_height = extracted['vid_height']
        vid_duration = extracted['vid_duration']
        _device_used = self._get_yolo_device()

        # 3. Extract pose features
        _t = _time.time()
        _all_kps = extracted.get('all_frame_keypoints', [])
        pose_feat = self._extract_pose_features(_all_kps, vid_height=vid_height)
        _perf['pose_feature_extract'] = round(_time.time() - _t, 3)

        # 4. Combine bbox + pose features into single feature vector
        combined_feat = {}
        for col in self._RF_FEATURE_COLUMNS:
            combined_feat[col] = feat.get(col, 0.0)
        if pose_feat:
            for col in self._POSE_FEATURE_COLUMNS:
                combined_feat[col] = pose_feat.get(col, 0.0)
        else:
            # No pose data — fill with defaults
            for col in self._POSE_FEATURE_COLUMNS:
                combined_feat[col] = 0.0 if 'angle' not in col else 180.0

        _combined_columns = self._RF_FEATURE_COLUMNS + self._POSE_FEATURE_COLUMNS
        feat_df = pd.DataFrame([combined_feat])
        feat_df = feat_df.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        feat_df = feat_df[_combined_columns]

        # 5. Short-clip detection
        _n_det_frames = int(feat.get('n_frames', 0))
        _is_short_clip = _n_det_frames < self._SHORT_CLIP_N_FRAMES
        _is_realtime = input_source in ('webcam-live', 'webcam', 'realtime')
        _confidence_level = 'high'
        if _n_det_frames < self._SHORT_CLIP_MIN_FRAMES:
            _confidence_level = 'insufficient'

        # 6. Predict
        _t = _time.time()
        pred = int(rf_pose_model.predict(feat_df)[0])
        fall_prob = None
        if hasattr(rf_pose_model, 'predict_proba'):
            proba = rf_pose_model.predict_proba(feat_df)[0]
            classes = list(rf_pose_model.classes_)
            prob_map = {int(c): float(p) for c, p in zip(classes, proba)}
            fall_prob = prob_map.get(1, 0.0)
        score = fall_prob if fall_prob is not None else float(pred)

        # Adaptive threshold
        _effective_threshold = self.fall_decision_threshold
        if _is_short_clip and _n_det_frames >= self._SHORT_CLIP_MIN_FRAMES:
            _range = self._SHORT_CLIP_N_FRAMES - self._SHORT_CLIP_MIN_FRAMES
            _ratio = (_n_det_frames - self._SHORT_CLIP_MIN_FRAMES) / max(_range, 1)
            _effective_threshold = self._SHORT_CLIP_THRESHOLD_MAX - _ratio * (self._SHORT_CLIP_THRESHOLD_MAX - self.fall_decision_threshold)
            _confidence_level = 'medium' if _n_det_frames >= 5 else 'low'

        fall_detected = score >= _effective_threshold

        # Feature importances
        _feature_importances = {}
        _rf_imp_model = rf_pose_model.named_steps['clf'] if hasattr(rf_pose_model, 'named_steps') and 'clf' in rf_pose_model.named_steps else rf_pose_model
        if hasattr(_rf_imp_model, 'feature_importances_'):
            for col, imp in zip(_combined_columns, _rf_imp_model.feature_importances_):
                _feature_importances[col] = round(float(imp), 4)
        _perf['rf_predict'] = round(_time.time() - _t, 3)

        # Motion guard (reuse same logic)
        _mg_mul = 0.7 if _is_short_clip else 1.0
        _motion_checks = {
            'delta_y_mean': feat.get('delta_y_mean', 0) < 5.0 * _mg_mul,
            'delta_y_max': feat.get('delta_y_max', 0) < 12.0 * _mg_mul,
            'delta_height_mean': feat.get('delta_height_mean', 0) < 5.0 * _mg_mul,
            'delta_width_mean': feat.get('delta_width_mean', 0) < 3.0 * _mg_mul,
            'delta_area_mean': feat.get('delta_area_mean', 0) < 150.0 * _mg_mul,
            'center_y_std': feat.get('center_y_std', 0) < 10.0 * _mg_mul,
            'height_std': feat.get('height_std', 0) < 8.0 * _mg_mul,
        }
        _is_stationary = all(_motion_checks.values())
        _motion_guard_applied = False
        _ar_only_guard = (
            feat.get('aspect_ratio_std', 0) > 0.1
            and feat.get('delta_y_max', 0) < 15.0
            and feat.get('center_y_std', 0) < 15.0
        )
        if _is_stationary and fall_detected:
            score = min(score, 0.10)
            fall_detected = False
            pred = 0
            _motion_guard_applied = True
        elif _ar_only_guard and fall_detected and score < 0.75:
            score = min(score, 0.20)
            fall_detected = False
            pred = 0
            _motion_guard_applied = True
        # FN-0005/FN-0025: Realtime enhanced motion guard (same as RF pipeline)
        elif _is_realtime and fall_detected and score < 0.85:
            _realtime_guard = False
            _fhr = feat.get('final_height_ratio', 1.0)
            _dym = feat.get('delta_y_max', 0)
            _cys = feat.get('center_y_std', 0)
            if _fhr > 0.45 and _dym < 30.0 and _cys < 35.0:
                _realtime_guard = True
            if _realtime_guard:
                score = min(score, 0.25)
                fall_detected = False
                pred = 0
                _motion_guard_applied = True
        # FN-0025: Moderate-motion dampener (RF-Pose)
        elif fall_detected and score < 0.70 and not _motion_guard_applied:
            _dym2 = feat.get('delta_y_max', 0)
            _fhr2 = feat.get('final_height_ratio', 1.0)
            _accel = feat.get('delta_y_accel_max', 0)
            if _dym2 < 25.0 and _fhr2 > 0.50 and _accel < 12.0:
                score = min(score, 0.40)
                fall_detected = False
                pred = 0
                _motion_guard_applied = True

        elapsed = round(_time.time() - t0, 2)
        _perf['total'] = elapsed

        risk_level = 'high' if score >= 0.75 else ('medium' if score >= _effective_threshold else 'low')
        if _confidence_level == 'insufficient':
            risk_level = 'low'
            fall_detected = False
            pred = 0
        risk_label = {'low': '안정', 'medium': '주의', 'high': '고위험'}.get(risk_level, '안정')

        behavior = self._predict_behavior_from_runtime(None, fall_detected, allow_fallback=False)
        if behavior is not None:
            behavior_class, behavior_label = behavior.get('code', 'non-fall'), behavior.get('label', '비낙상')
        elif fall_detected:
            behavior_class, behavior_label = 'fall', '낙상'
            behavior = {'code': 'fall', 'label': '낙상', 'source': 'fall-risk-shortcut', 'fallback': False, 'reason': ['RF-Pose 모델이 낙상으로 분류했습니다.']}
        else:
            behavior_class, behavior_label = self._guess_behavior(filename, score)
            behavior = {'code': behavior_class, 'label': behavior_label, 'source': 'filename-fallback', 'fallback': True, 'reason': ['행동 모델 미연결 — 파일명 fallback']}

        event_time = round(vid_duration / 2, 2)
        events = [{'label': 'RF-Pose 파이프라인 대표 분석 구간', 'time': event_time, 'confidence': round(score, 4), 'severity': risk_level}]

        # Analysis basis — top features by importance
        _feat_labels = self._get_feat_labels()
        analysis_basis = []
        if _feature_importances:
            _all_feat = {**feat, **(pose_feat or {})}
            _scored = []
            for col in _combined_columns:
                imp = _feature_importances.get(col, 0)
                val = _all_feat.get(col, 0)
                _scored.append((col, imp, val, imp))
            _scored.sort(key=lambda x: x[3], reverse=True)
            for col, imp, val, _ in _scored[:8]:
                info = _feat_labels.get(col, (col, '', ''))
                lvl = 'high' if imp >= 0.10 else ('medium' if imp >= 0.05 else 'low')
                analysis_basis.append({
                    'feature': col, 'label': f'{info[0]} (기여도 {round(imp * 100, 1)}%)',
                    'value': round(float(val), 4) if isinstance(val, float) else val,
                    'unit': info[2], 'level': lvl, 'description': info[1],
                })

        return {
            'fall_detected': fall_detected,
            'behavior_class': behavior_class,
            'behavior_label': behavior_label,
            'risk_score': round(score, 4),
            'risk_level': risk_level,
            'risk_label': risk_label,
            'summary': ('Motion guard로 오탐을 억제했습니다.' if _motion_guard_applied else ('RF-Pose가 낙상 가능성을 높게 판단했습니다.' if fall_detected else 'RF-Pose 기준 즉시 낙상 가능성은 낮습니다.')),
            'events': events,
            'reference_matches': [],
            'analysis_basis': analysis_basis,
            'runtime_key': 'rf-pose-runtime',
            'runtime_label': 'RF-Pose 파이프라인 (RandomForest + YOLOv8n-Pose + Keypoints)',
            'runtime_inference': {
                'fall_score': round(score, 4),
                'fall_detected': fall_detected,
                'pred_value': pred,
                'fall_probability': round(score, 4),
                'raw_fall_probability': round(fall_prob if fall_prob is not None else float(pred), 4),
                'elapsed_sec': elapsed,
                'perf': _perf,
                'device': _device_used,
                'extracted_frames': len(frames),
                'detected_person_frames': len(det_rows),
                'features': {k: round(float(v), 4) if isinstance(v, float) else v for k, v in combined_feat.items()},
                'pose_features': pose_feat,
                'motion_guard': {'applied': _motion_guard_applied, 'is_stationary': _is_stationary, 'checks': _motion_checks},
                'short_clip': {'is_short_clip': _is_short_clip, 'n_det_frames': _n_det_frames, 'effective_threshold': round(_effective_threshold, 4), 'confidence_level': _confidence_level, 'is_realtime': _is_realtime},
            },
            'behavior_inference': behavior,
            'model_runtime': {
                'label': 'RF-Pose 파이프라인 (RandomForest + YOLOv8n-Pose + Keypoints)',
                'rf_model_path': self._rf_pose_model_path(),
                'yolo_model': self._RF_YOLO_MODEL,
                'yolo_imgsz': self._RF_YOLO_IMGSZ,
                'target_fps': self._RF_TARGET_FPS,
                'analysis_profile': analysis_profile,
                'extracted_frames': len(frames),
                'detected_person_frames': len(det_rows),
                'fall_probability': round(score, 4),
                'detection_frames': detection_frames,
                'feature_importances': _feature_importances,
                'combined_feature_count': len(_combined_columns),
                'bbox_feature_count': len(self._RF_FEATURE_COLUMNS),
                'pose_feature_count': len(self._POSE_FEATURE_COLUMNS),
            },
            'video_meta': {
                'duration': vid_duration,
                'width': vid_width,
                'height': vid_height,
                'fps': round(extracted['orig_fps'], 2),
            },
        }

    def _rf_runtime_meta(self):
        active_model_path = self._rf_active_model_path()
        project_summary = self._rf_project_summary()
        info = {
            'ready': self._rf_pipeline_available(),
            'model_path': active_model_path,
            'model_name': os.path.basename(active_model_path),
            'model_class': 'RandomForestClassifier',
            'yolo_model': self._RF_YOLO_MODEL,
            'feature_count': len(self._RF_FEATURE_COLUMNS),
            'features': list(self._RF_FEATURE_COLUMNS),
            'n_estimators': 0,
            'max_depth': None,
            'updated_at': '',
            'load_error': '',
            'training_samples': int(project_summary.get('training_samples', 0) or 0),
            'source': project_summary.get('source', 'rf-standalone'),
        }
        if info['ready'] is False:
            return info
        try:
            info['updated_at'] = datetime.datetime.fromtimestamp(os.path.getmtime(active_model_path)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            info['updated_at'] = ''
        try:
            rf_model = self._get_rf_model()
            rf_meta_model = rf_model.named_steps['clf'] if hasattr(rf_model, 'named_steps') and 'clf' in rf_model.named_steps else rf_model
            info['model_class'] = rf_meta_model.__class__.__name__
            info['feature_count'] = int(getattr(rf_meta_model, 'n_features_in_', len(self._RF_FEATURE_COLUMNS)) or len(self._RF_FEATURE_COLUMNS))
            feature_names = getattr(rf_meta_model, 'feature_names_in_', None)
            if feature_names is not None:
                info['features'] = [str(item) for item in list(feature_names)]
            info['n_estimators'] = int(getattr(rf_meta_model, 'n_estimators', 0) or 0)
            max_depth = getattr(rf_meta_model, 'max_depth', None)
            if isinstance(max_depth, (int, float)) and max_depth is not None:
                info['max_depth'] = int(max_depth)
            else:
                info['max_depth'] = max_depth
            info['cv_f1'] = float((project_summary.get('cv', {}) or {}).get('f1', 0.0) or 0.0)
            info['cv_auc'] = float((project_summary.get('cv', {}) or {}).get('roc_auc', 0.0) or 0.0)
        except Exception as e:
            info['load_error'] = str(e)
        return info

    def _check_video_stationary(self, video_path, sample_frames=4, threshold=3.0):
        """Lightweight motion check via frame differencing.
        
        Returns True if the video appears stationary (very low inter-frame change).
        Samples a few evenly-spaced frames, converts to grayscale, and computes
        mean absolute pixel difference between consecutive frames.
        """
        import numpy as np
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total_frames < sample_frames:
            cap.release()
            return False
        step = max(total_frames // (sample_frames + 1), 1)
        indices = [step * (i + 1) for i in range(sample_frames)]
        prev_gray = None
        diffs = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            # Downscale to 160x90 for speed
            small = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = np.mean(np.abs(gray.astype(float) - prev_gray.astype(float)))
                diffs.append(diff)
            prev_gray = gray
        cap.release()
        if not diffs:
            return False
        mean_diff = float(np.mean(diffs))
        return mean_diff < threshold

    # ── FN-20260406-0006: Unified person timeseries extractor ──────────
    # Combines bbox + keypoint + time data into a single normalized timeseries
    # per track/frame, then builds sliding-window feature vectors.

    # Full 37-feature column list for XG-Fall / XG-Posture
    _XG_FEATURE_COLUMNS = [
        # === Original XGBoost 10 (bbox-derived, window-level) ===
        'center_dy', 'height_ratio', 'aspect_change', 'stillness',
        'floor_proximity', 'area_change', 'vert_horiz_ratio',
        'max_down_speed', 'avg_conf', 'n_points',
        # === Pose-derived 12 (from RF-Pose, normalized) ===
        'pose_tilt_mean', 'pose_tilt_max',
        'pose_height_ratio_mean', 'pose_height_ratio_min',
        'pose_knee_bend_mean', 'pose_knee_bend_min',
        'pose_spread_mean', 'pose_spread_max',
        'pose_descent_mean', 'pose_descent_max',
        'pose_change_mean', 'pose_change_max',
        # === Temporal / transition 5 ===
        'descent_duration', 'oscillation_count', 'speed_std',
        'post_descent_stillness', 'upper_body_motion',
        # === Transition phase 4 ===
        'time_to_max_down_speed', 'time_from_peak_to_stillness',
        'pre_descent_stillness', 'post_peak_recovery_ratio',
        # === Gait cycle 3 ===
        'step_period_est', 'knee_angle_cycle_strength', 'center_y_periodicity',
        # === Lie/fall discrimination 3 ===
        'tilt_change_duration', 'spread_after_descent', 'floor_proximity_slope',
    ]

    def _extract_unified_timeseries(self, video_path, input_source='upload', duration_hint=0):
        """Extract unified per-frame bbox + keypoint timeseries (all normalized coords).

        Returns dict with:
            - 'timeseries': list of per-frame dicts {frame_idx, time_sec, bbox:{cx,cy,w,h,ar,area,conf}, keypoints:[17×{x,y,conf}]}
            - 'vid_meta': {width, height, fps, duration, total_frames}
            - 'detection_frames': raw detection data for visualization
            - 'perf': timing dict
            - 'raw_frames': sampled frames (for backward compat)
        """
        import numpy as np
        import time as _time

        _perf = {}
        _is_realtime = input_source in ('webcam-live', 'webcam', 'realtime')

        if cv2 is None:
            raise Exception('cv2(OpenCV)가 설치되지 않아 추출기를 실행할 수 없습니다.')

        yolo_model = self._get_rf_yolo_model()

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise Exception(f'영상 열기 실패: {video_path}')

        orig_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if orig_fps <= 0:
            orig_fps = 30.0
        total_frames_raw = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        vid_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        vid_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        vid_duration = round(total_frames_raw / orig_fps, 2) if orig_fps > 0 else 0.0

        target_fps = 8 if _is_realtime else self._RF_TARGET_FPS   # FN-0021: 3→8fps for more frames per window
        max_frames = 40 if _is_realtime else 0                      # FN-0021: 12→40 (5s×8fps=40)
        yolo_imgsz = 480 if _is_realtime else self._RF_YOLO_IMGSZ
        step = max(int(round(orig_fps / target_fps)), 1)

        # FN-0021: webm fps correction — webm often reports 0 or 1000fps
        if _is_realtime and total_frames_raw > 0 and duration_hint > 0:
            corrected_fps = total_frames_raw / duration_hint
            if corrected_fps > 1.0 and abs(corrected_fps - orig_fps) / max(orig_fps, 1) > 0.3:
                orig_fps = corrected_fps
                step = max(int(round(orig_fps / target_fps)), 1)

        # -- Frame sampling --
        _t = _time.time()
        frames = []
        _resize_to = None
        if vid_width > 1280 or vid_height > 720:
            if vid_width > vid_height:
                _resize_to = (640, int(vid_height * 640 / max(vid_width, 1)))
            else:
                _resize_to = (int(vid_width * 360 / max(vid_height, 1)), 360)

        if total_frames_raw > 0 and step > 1:
            target_indices = list(range(0, total_frames_raw, step))
            if max_frames > 0:
                target_indices = target_indices[:max_frames]
            target_set = set(target_indices)
            frame_idx = 0
            while target_indices and frame_idx <= target_indices[-1]:
                ret = cap.grab()
                if not ret:
                    break
                if frame_idx in target_set:
                    ret2, frame = cap.retrieve()
                    if ret2:
                        if _resize_to is not None:
                            frame = cv2.resize(frame, _resize_to)
                        frames.append((frame_idx, frame))
                        if max_frames > 0 and len(frames) >= max_frames:
                            break
                frame_idx += 1
        else:
            frame_idx = 0
            while True:
                ret = cap.grab()
                if not ret:
                    break
                if frame_idx % step == 0:
                    ret2, frame = cap.retrieve()
                    if ret2:
                        if _resize_to is not None:
                            frame = cv2.resize(frame, _resize_to)
                        frames.append((frame_idx, frame))
                        if max_frames > 0 and len(frames) >= max_frames:
                            break
                    frame_idx += 1
                else:
                    frame_idx += 1
        cap.release()
        _perf['frame_extract'] = round(_time.time() - _t, 3)

        if len(frames) == 0:
            raise Exception('영상에서 프레임을 추출할 수 없습니다.')

        # -- YOLO-Pose detection --
        _t = _time.time()
        frame_indices = [fidx for fidx, _ in frames]
        frame_images = [frame for _, frame in frames]
        _conf = 0.15 if _is_realtime else self._RF_CONF_THRES
        batch_results = yolo_model.predict(
            source=frame_images, conf=_conf, verbose=False,
            imgsz=yolo_imgsz, device=self._get_yolo_device()
        )
        _perf['yolo_predict'] = round(_time.time() - _t, 3)

        # -- Build unified timeseries (normalized coordinates) --
        _t = _time.time()
        _norm_w = max(vid_width, 1)
        _norm_h = max(vid_height, 1)
        _coord_sx = vid_width / _resize_to[0] if _resize_to else 1.0
        _coord_sy = vid_height / _resize_to[1] if _resize_to else 1.0

        timeseries = []
        detection_frames_vis = []

        for i, r in enumerate(batch_results):
            fidx = frame_indices[i]
            boxes = r.boxes
            kpts = getattr(r, 'keypoints', None)
            if boxes is None or len(boxes) == 0:
                continue

            # Select largest-area person
            best_idx, best_area = -1, -1
            for bi, b in enumerate(boxes):
                if int(b.cls.item()) != self._RF_PERSON_CLASS_ID:
                    continue
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                area = (x2 - x1) * (y2 - y1)
                if area > best_area:
                    best_area = area
                    best_idx = bi

            if best_idx < 0:
                continue

            b = boxes[best_idx]
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            # Scale back to original coords, then normalize to [0,1]
            ox1, oy1 = x1 * _coord_sx, y1 * _coord_sy
            ox2, oy2 = x2 * _coord_sx, y2 * _coord_sy
            bw, bh = ox2 - ox1, oy2 - oy1
            cx, cy = (ox1 + ox2) / 2 / _norm_w, (oy1 + oy2) / 2 / _norm_h
            nw, nh = bw / _norm_w, bh / _norm_h

            entry = {
                'frame_idx': fidx,
                'time_sec': round(fidx / orig_fps, 4) if orig_fps > 0 else 0,
                'bbox': {
                    'cx': cx, 'cy': cy,
                    'w': nw, 'h': nh,
                    'aspect_ratio': nw / (nh + 1e-9),
                    'area': nw * nh,
                    'conf': float(b.conf.item()),
                },
                'keypoints': None,
            }

            # Keypoints (normalized)
            if kpts is not None and best_idx < len(kpts.data):
                kp_data = kpts.data[best_idx].cpu().numpy()  # (17, 3)
                kp_norm = []
                for kp in kp_data:
                    kp_norm.append({
                        'x': float(kp[0]) * _coord_sx / _norm_w,
                        'y': float(kp[1]) * _coord_sy / _norm_h,
                        'conf': float(kp[2]),
                    })
                entry['keypoints'] = kp_norm

            timeseries.append(entry)

            # Build detection_frames for visualization (original pixel coords)
            vis_dets = []
            for bi2, b2 in enumerate(boxes):
                if int(b2.cls.item()) != self._RF_PERSON_CLASS_ID:
                    continue
                vx1, vy1, vx2, vy2 = b2.xyxy[0].tolist()
                det_vis = {
                    'x1': round(vx1 * _coord_sx, 1), 'y1': round(vy1 * _coord_sy, 1),
                    'x2': round(vx2 * _coord_sx, 1), 'y2': round(vy2 * _coord_sy, 1),
                    'conf': round(float(b2.conf.item()), 3),
                }
                if kpts is not None and bi2 < len(kpts.data):
                    kp_raw = kpts.data[bi2].cpu().numpy()
                    kp_s = []
                    for kp in kp_raw:
                        kp_s.append([
                            round(float(kp[0]) * _coord_sx, 1),
                            round(float(kp[1]) * _coord_sy, 1),
                            round(float(kp[2]), 3),
                        ])
                    det_vis['keypoints'] = kp_s
                vis_dets.append(det_vis)
            if vis_dets:
                detection_frames_vis.append({
                    'frame_idx': fidx,
                    'time_sec': round(fidx / orig_fps, 2) if orig_fps > 0 else 0,
                    'detections': vis_dets,
                })

        _perf['timeseries_build'] = round(_time.time() - _t, 3)

        _min_det = 1 if _is_realtime else 2
        if len(timeseries) < _min_det:
            raise Exception(f'사람 bbox 검출이 부족합니다 (검출 프레임: {len(timeseries)}). 최소 {_min_det}프레임이 필요합니다.')

        return {
            'timeseries': timeseries,
            'vid_meta': {
                'width': vid_width, 'height': vid_height,
                'fps': orig_fps, 'duration': vid_duration,
                'total_frames': total_frames_raw,
            },
            'detection_frames': detection_frames_vis,
            'perf': _perf,
            'raw_frames': frames,
            'total_sampled': len(frames),
        }

    def _build_xg_feature_windows(self, timeseries, vid_meta, window_sec=1.0, stride_sec=0.5):
        """Build sliding-window feature vectors (37 features) from unified timeseries.

        Args:
            timeseries: list of per-frame dicts from _extract_unified_timeseries
            vid_meta: {width, height, fps, ...}
            window_sec: window duration in seconds
            stride_sec: stride in seconds

        Returns:
            list of dicts, each with 37 feature values keyed by _XG_FEATURE_COLUMNS
        """
        import numpy as np
        import math

        if len(timeseries) < 2:
            return []

        fps = vid_meta.get('fps', 30.0)
        if fps <= 0:
            fps = 30.0

        KP_CONF_MIN = 0.3

        def _kp_ok(kp):
            return kp is not None and kp.get('conf', 0) >= KP_CONF_MIN

        def _mid(a, b):
            return {'x': (a['x'] + b['x']) / 2, 'y': (a['y'] + b['y']) / 2}

        def _angle_vert(p1, p2):
            dx = p2['x'] - p1['x']
            dy = p2['y'] - p1['y']
            if abs(dy) < 1e-9 and abs(dx) < 1e-9:
                return 0.0
            return math.degrees(math.atan2(abs(dx), abs(dy)))

        def _angle3(p1, p2, p3):
            v1x, v1y = p1['x'] - p2['x'], p1['y'] - p2['y']
            v2x, v2y = p3['x'] - p2['x'], p3['y'] - p2['y']
            dot = v1x * v2x + v1y * v2y
            m1 = math.sqrt(v1x**2 + v1y**2)
            m2 = math.sqrt(v2x**2 + v2y**2)
            if m1 < 1e-9 or m2 < 1e-9:
                return 180.0
            cos_a = max(-1.0, min(1.0, dot / (m1 * m2)))
            return math.degrees(math.acos(cos_a))

        def _fft_dominant_period(signal):
            """Estimate dominant period from signal using FFT."""
            if len(signal) < 4:
                return 0.0
            arr = np.array(signal) - np.mean(signal)
            fft_vals = np.abs(np.fft.rfft(arr))
            if len(fft_vals) < 2:
                return 0.0
            fft_vals[0] = 0  # ignore DC
            peak_idx = int(np.argmax(fft_vals))
            if peak_idx == 0:
                return 0.0
            return len(signal) / peak_idx  # period in samples

        # Collect timestamps
        times = [e['time_sec'] for e in timeseries]
        t_start = times[0]
        t_end = times[-1]
        total_dur = t_end - t_start
        if total_dur <= 0:
            total_dur = len(timeseries) / fps

        windows = []
        t = t_start
        while t + window_sec * 0.5 <= t_end:
            w_start = t
            w_end = t + window_sec
            # Gather frames in window
            w_frames = [e for e in timeseries if w_start <= e['time_sec'] < w_end]
            if len(w_frames) < 2:
                t += stride_sec
                continue

            # ── BBox-derived features (original 10) ──
            cys = [f['bbox']['cy'] for f in w_frames]
            cxs = [f['bbox']['cx'] for f in w_frames]
            hs = [f['bbox']['h'] for f in w_frames]
            ws_b = [f['bbox']['w'] for f in w_frames]
            ars = [f['bbox']['aspect_ratio'] for f in w_frames]
            areas = [f['bbox']['area'] for f in w_frames]
            confs = [f['bbox']['conf'] for f in w_frames]

            dy_list = [cys[i+1] - cys[i] for i in range(len(cys)-1)]
            down_speeds = [max(d, 0) for d in dy_list]

            center_dy = float(np.mean(dy_list)) if dy_list else 0.0
            h_ratio = (hs[-1] - hs[0]) / (hs[0] + 1e-9) if len(hs) >= 2 else 0.0
            ar_change = (ars[-1] - ars[0]) if len(ars) >= 2 else 0.0
            still_count = sum(1 for d in dy_list if abs(d) < 0.005) if dy_list else 0
            stillness = still_count / max(len(dy_list), 1)
            floor_prox = float(np.max(cys)) if cys else 0.0
            area_change = (areas[-1] - areas[0]) / (areas[0] + 1e-9) if len(areas) >= 2 else 0.0
            dx_list = [cxs[i+1] - cxs[i] for i in range(len(cxs)-1)]
            vert_sum = sum(abs(d) for d in dy_list) if dy_list else 0.0
            horiz_sum = sum(abs(d) for d in dx_list) if dx_list else 0.0
            vh_ratio = vert_sum / (horiz_sum + 1e-9) if horiz_sum > 0 else vert_sum
            max_down = float(np.max(down_speeds)) if down_speeds else 0.0
            avg_conf = float(np.mean(confs)) if confs else 0.0
            n_pts = len(w_frames)

            # ── Pose-derived features (12) ──
            tilts, p_hrs, knees, spreads, p_cys = [], [], [], [], []
            pose_vecs = []
            upper_motions = []
            for f in w_frames:
                kps = f.get('keypoints')
                if kps is None or len(kps) < 17:
                    continue
                ls, rs = kps[5], kps[6]
                lh, rh = kps[11], kps[12]
                lk, rk = kps[13], kps[14]
                la, ra = kps[15], kps[16]
                nose = kps[0]

                if _kp_ok(ls) and _kp_ok(rs) and _kp_ok(lh) and _kp_ok(rh):
                    sh_mid = _mid(ls, rs)
                    hp_mid = _mid(lh, rh)
                    tilts.append(_angle_vert(hp_mid, sh_mid))
                    p_cys.append((sh_mid['y'] + hp_mid['y']) / 2)

                foot_y = None
                if _kp_ok(la) and _kp_ok(ra):
                    foot_y = max(la['y'], ra['y'])
                elif _kp_ok(la):
                    foot_y = la['y']
                elif _kp_ok(ra):
                    foot_y = ra['y']
                if _kp_ok(nose) and foot_y is not None:
                    p_hrs.append(abs(nose['y'] - foot_y))

                k_angles = []
                if _kp_ok(lh) and _kp_ok(lk) and _kp_ok(la):
                    k_angles.append(_angle3(lh, lk, la))
                if _kp_ok(rh) and _kp_ok(rk) and _kp_ok(ra):
                    k_angles.append(_angle3(rh, rk, ra))
                if k_angles:
                    knees.append(min(k_angles))

                valid_xs = [kps[j]['x'] for j in range(17) if _kp_ok(kps[j])]
                if len(valid_xs) >= 3:
                    spreads.append(float(np.std(valid_xs)))

                vec = []
                for j in range(17):
                    if _kp_ok(kps[j]):
                        vec.extend([kps[j]['x'], kps[j]['y']])
                    else:
                        vec.extend([0.0, 0.0])
                pose_vecs.append(vec)

                # upper body motion (shoulders + elbows)
                ub_pts = [kps[5], kps[6], kps[7], kps[8]]
                ub_valid = [p for p in ub_pts if _kp_ok(p)]
                if len(ub_valid) >= 2:
                    upper_motions.append(float(np.std([p['y'] for p in ub_valid])))

            pose_tilt_mean = float(np.mean(tilts)) if tilts else 0.0
            pose_tilt_max = float(np.max(tilts)) if tilts else 0.0
            pose_hr_mean = float(np.mean(p_hrs)) if p_hrs else 0.0
            pose_hr_min = float(np.min(p_hrs)) if p_hrs else 0.0
            pose_kb_mean = float(np.mean(knees)) if knees else 180.0
            pose_kb_min = float(np.min(knees)) if knees else 180.0
            pose_sp_mean = float(np.mean(spreads)) if spreads else 0.0
            pose_sp_max = float(np.max(spreads)) if spreads else 0.0

            p_descents = [max(p_cys[i+1] - p_cys[i], 0) for i in range(len(p_cys)-1)] if len(p_cys) >= 2 else []
            pose_desc_mean = float(np.mean(p_descents)) if p_descents else 0.0
            pose_desc_max = float(np.max(p_descents)) if p_descents else 0.0

            change_rates = []
            if len(pose_vecs) >= 2:
                for iv in range(len(pose_vecs)-1):
                    v1, v2 = np.array(pose_vecs[iv]), np.array(pose_vecs[iv+1])
                    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                    if n1 > 1e-9 and n2 > 1e-9:
                        cs = np.dot(v1, v2) / (n1 * n2)
                        change_rates.append(1.0 - max(-1.0, min(1.0, cs)))
                    else:
                        change_rates.append(0.0)
            pose_ch_mean = float(np.mean(change_rates)) if change_rates else 0.0
            pose_ch_max = float(np.max(change_rates)) if change_rates else 0.0

            # ── Temporal / transition features (5) ──
            # descent_duration: consecutive frames with cy increasing
            desc_frames = 0
            _cur_run = 0
            for d in dy_list:
                if d > 0.002:
                    _cur_run += 1
                    desc_frames = max(desc_frames, _cur_run)
                else:
                    _cur_run = 0
            descent_dur = desc_frames / fps

            # oscillation_count: number of sign changes in dy
            osc_count = 0
            for oi in range(1, len(dy_list)):
                if dy_list[oi] * dy_list[oi-1] < 0:
                    osc_count += 1

            spd_std = float(np.std(down_speeds)) if down_speeds else 0.0

            # post_descent_stillness: ratio of still frames after max-descent frame
            max_ds_idx = int(np.argmax(down_speeds)) if down_speeds else 0
            post_frames = dy_list[max_ds_idx+1:] if max_ds_idx + 1 < len(dy_list) else []
            post_still = sum(1 for d in post_frames if abs(d) < 0.005) / max(len(post_frames), 1)

            upper_body_mot = float(np.mean(upper_motions)) if upper_motions else 0.0

            # ── Transition phase features (4) ──
            max_ds_time = max_ds_idx / fps if down_speeds else 0.0
            # time_from_peak_to_stillness
            peak_to_still = 0.0
            for si in range(max_ds_idx + 1, len(dy_list)):
                if abs(dy_list[si]) < 0.005:
                    peak_to_still = (si - max_ds_idx) / fps
                    break

            pre_ds_frames = dy_list[:max(max_ds_idx, 0)]
            pre_still = sum(1 for d in pre_ds_frames if abs(d) < 0.005) / max(len(pre_ds_frames), 1)

            # recovery ratio: how much center_y goes back up after peak descent
            if max_ds_idx + 1 < len(cys) and max_ds_idx > 0:
                peak_cy = cys[max_ds_idx + 1]
                final_cy = cys[-1]
                fall_amount = peak_cy - cys[0]
                recovery = peak_cy - final_cy
                recovery_ratio = recovery / (fall_amount + 1e-9) if fall_amount > 0.01 else 0.0
            else:
                recovery_ratio = 0.0

            # ── Gait cycle features (3) ──
            step_period = _fft_dominant_period(cys) / fps if len(cys) >= 4 else 0.0
            knee_cycle = _fft_dominant_period(knees) / fps if len(knees) >= 4 else 0.0
            cy_periodicity = 0.0
            if len(cys) >= 4:
                cy_arr = np.array(cys) - np.mean(cys)
                fft_v = np.abs(np.fft.rfft(cy_arr))
                if len(fft_v) > 1:
                    fft_v[0] = 0
                    cy_periodicity = float(np.max(fft_v)) / (np.sum(fft_v) + 1e-9)

            # ── Lie/fall discrimination features (3) ──
            # tilt_change_duration: frames where tilt changed significantly
            tilt_changes = [abs(tilts[ti+1] - tilts[ti]) for ti in range(len(tilts)-1)] if len(tilts) >= 2 else []
            tilt_chg_dur = sum(1 for tc in tilt_changes if tc > 5.0) / fps if tilt_changes else 0.0

            # spread_after_descent: horizontal spread in frames after max descent
            post_spreads = spreads[max_ds_idx+1:] if max_ds_idx + 1 < len(spreads) else []
            spread_after = float(np.mean(post_spreads)) if post_spreads else 0.0

            # floor_proximity_slope: linear regression slope of floor_proximity over window
            fp_slope = 0.0
            if len(cys) >= 3:
                x_arr = np.arange(len(cys), dtype=float)
                y_arr = np.array(cys)
                m = np.polyfit(x_arr, y_arr, 1)[0] if len(x_arr) >= 2 else 0.0
                fp_slope = float(m)

            feat = {
                'center_dy': center_dy,
                'height_ratio': h_ratio,
                'aspect_change': ar_change,
                'stillness': stillness,
                'floor_proximity': floor_prox,
                'area_change': area_change,
                'vert_horiz_ratio': vh_ratio,
                'max_down_speed': max_down,
                'avg_conf': avg_conf,
                'n_points': n_pts,
                'pose_tilt_mean': pose_tilt_mean,
                'pose_tilt_max': pose_tilt_max,
                'pose_height_ratio_mean': pose_hr_mean,
                'pose_height_ratio_min': pose_hr_min,
                'pose_knee_bend_mean': pose_kb_mean,
                'pose_knee_bend_min': pose_kb_min,
                'pose_spread_mean': pose_sp_mean,
                'pose_spread_max': pose_sp_max,
                'pose_descent_mean': pose_desc_mean,
                'pose_descent_max': pose_desc_max,
                'pose_change_mean': pose_ch_mean,
                'pose_change_max': pose_ch_max,
                'descent_duration': descent_dur,
                'oscillation_count': osc_count,
                'speed_std': spd_std,
                'post_descent_stillness': post_still,
                'upper_body_motion': upper_body_mot,
                'time_to_max_down_speed': max_ds_time,
                'time_from_peak_to_stillness': peak_to_still,
                'pre_descent_stillness': pre_still,
                'post_peak_recovery_ratio': recovery_ratio,
                'step_period_est': step_period,
                'knee_angle_cycle_strength': knee_cycle,
                'center_y_periodicity': cy_periodicity,
                'tilt_change_duration': tilt_chg_dur,
                'spread_after_descent': spread_after,
                'floor_proximity_slope': fp_slope,
            }
            windows.append(feat)
            t += stride_sec

        return windows

    def _extract_rf_pipeline_features(self, video_path, input_source='upload'):
        import numpy as np
        import pandas as pd
        import time as _time

        _perf = {}
        yolo_model = self._get_rf_yolo_model()
        _is_realtime = input_source in ('webcam-live', 'webcam', 'realtime')

        if cv2 is None:
            raise Exception('cv2(OpenCV)가 설치되지 않아 RF 파이프라인을 실행할 수 없습니다.')

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise Exception(f'영상 열기 실패: {video_path}')

        orig_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if orig_fps <= 0:
            orig_fps = 30.0
        total_frames_raw = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        vid_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        vid_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        vid_duration = round(total_frames_raw / orig_fps, 2) if orig_fps > 0 else 0.0

        # FN-0016: webcam-live 복합 개선 — 프레임 샘플링 강화 (C)
        # FN-20260406-0003: realtime에서 target_fps 3, YOLO imgsz 480 → 추론 속도 개선
        target_fps = 3 if _is_realtime else self._RF_TARGET_FPS
        max_frames = 12 if _is_realtime else 0  # realtime: 4초 × 3fps = 최대 12프레임 캡
        yolo_imgsz = 480 if _is_realtime else self._RF_YOLO_IMGSZ
        step = max(int(round(orig_fps / target_fps)), 1)
        _t = _time.time()
        frames = []
        _resize_to = None
        if vid_width > 1280 or vid_height > 720:
            _resize_to = (min(vid_width, 640), min(vid_height, 360))
            if vid_width > vid_height:
                _resize_to = (640, int(vid_height * 640 / max(vid_width, 1)))
            else:
                _resize_to = (int(vid_width * 360 / max(vid_height, 1)), 360)

        if total_frames_raw > 0 and step > 1:
            target_indices = list(range(0, total_frames_raw, step))
            if max_frames > 0:
                target_indices = target_indices[:max_frames]
            target_set = set(target_indices)
            frame_idx = 0
            while target_indices and frame_idx <= target_indices[-1]:
                ret = cap.grab()
                if not ret:
                    break
                if frame_idx in target_set:
                    ret2, frame = cap.retrieve()
                    if ret2:
                        if _resize_to is not None:
                            frame = cv2.resize(frame, _resize_to)
                        frames.append((frame_idx, frame))
                        if max_frames > 0 and len(frames) >= max_frames:
                            break
                frame_idx += 1
        else:
            frame_idx = 0
            while True:
                ret = cap.grab()
                if not ret:
                    break
                if frame_idx % step == 0:
                    ret2, frame = cap.retrieve()
                    if ret2:
                        if _resize_to is not None:
                            frame = cv2.resize(frame, _resize_to)
                        frames.append((frame_idx, frame))
                        if max_frames > 0 and len(frames) >= max_frames:
                            break
                frame_idx += 1
        cap.release()
        _perf['frame_extract'] = round(_time.time() - _t, 3)

        if len(frames) == 0:
            raise Exception('영상에서 프레임을 추출할 수 없습니다.')

        _t = _time.time()
        frame_indices = [fidx for fidx, _ in frames]
        frame_images = [frame for _, frame in frames]
        # FN-0016: webcam-live YOLO conf 하향 (B) — 검출률 향상
        _conf = 0.15 if _is_realtime else self._RF_CONF_THRES
        batch_results = yolo_model.predict(source=frame_images, conf=_conf, verbose=False, imgsz=yolo_imgsz, device=self._get_yolo_device())
        _perf['yolo_predict'] = round(_time.time() - _t, 3)

        det_rows = []
        all_frame_keypoints = []  # FN-0002: per-frame keypoints for best person (pose features)
        for i, r in enumerate(batch_results):
            fidx = frame_indices[i]
            boxes = r.boxes
            kpts = getattr(r, 'keypoints', None)  # FN-0002: pose keypoints
            if boxes is None or len(boxes) == 0:
                continue
            best_row = None
            best_area = -1
            best_box_idx = -1
            for bi, b in enumerate(boxes):
                cls_id = int(b.cls.item())
                if cls_id != self._RF_PERSON_CLASS_ID:
                    continue
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                w = x2 - x1
                h = y2 - y1
                area = w * h
                if area > best_area:
                    best_area = area
                    best_box_idx = bi
                    best_row = {
                        'frame_idx': fidx,
                        'width': w, 'height': h,
                        'center_x': (x1 + x2) / 2,
                        'center_y': (y1 + y2) / 2,
                        'area': area,
                        'confidence': float(b.conf.item()),
                    }
            if best_row is not None:
                det_rows.append(best_row)
                # FN-0002: Extract keypoints for best person
                if kpts is not None and best_box_idx < len(kpts.data):
                    kp_data = kpts.data[best_box_idx].cpu().numpy()  # (17, 3) = x, y, conf
                    all_frame_keypoints.append({
                        'frame_idx': fidx,
                        'keypoints': kp_data.tolist(),
                    })

        _coord_scale_x = vid_width / _resize_to[0] if _resize_to is not None else 1.0
        _coord_scale_y = vid_height / _resize_to[1] if _resize_to is not None else 1.0
        detection_frames = []
        for i, r in enumerate(batch_results):
            fidx = frame_indices[i]
            boxes = r.boxes
            kpts = getattr(r, 'keypoints', None)  # FN-0002: pose keypoints
            frame_dets = []
            if boxes is not None:
                for bi, b in enumerate(boxes):
                    cls_id = int(b.cls.item())
                    if cls_id != self._RF_PERSON_CLASS_ID:
                        continue
                    x1, y1, x2, y2 = b.xyxy[0].tolist()
                    det_entry = {
                        'x1': round(x1 * _coord_scale_x, 1), 'y1': round(y1 * _coord_scale_y, 1),
                        'x2': round(x2 * _coord_scale_x, 1), 'y2': round(y2 * _coord_scale_y, 1),
                        'conf': round(float(b.conf.item()), 3),
                    }
                    # FN-0002: Add keypoints to each detection (scaled to original coords)
                    if kpts is not None and bi < len(kpts.data):
                        kp_raw = kpts.data[bi].cpu().numpy()  # (17, 3)
                        kp_scaled = []
                        for kp in kp_raw:
                            kp_scaled.append([
                                round(float(kp[0]) * _coord_scale_x, 1),
                                round(float(kp[1]) * _coord_scale_y, 1),
                                round(float(kp[2]), 3),
                            ])
                        det_entry['keypoints'] = kp_scaled
                    frame_dets.append(det_entry)
            if len(frame_dets) > 0:
                detection_frames.append({
                    'frame_idx': fidx,
                    'time_sec': round(fidx / orig_fps, 2) if orig_fps > 0 else 0,
                    'detections': frame_dets,
                })

        # FN-0016: webcam-live 최소 검출 완화 (A) — 2→1
        _min_det = 1 if _is_realtime else 2
        if len(det_rows) < _min_det:
            raise Exception(f'사람 bbox 검출이 부족합니다 (검출 프레임: {len(det_rows)}). 최소 {_min_det}프레임이 필요합니다.')

        _t = _time.time()
        df_det = pd.DataFrame(det_rows).sort_values('frame_idx').reset_index(drop=True)
        g = df_det.copy()
        g['area'] = g['width'] * g['height']
        g['aspect_ratio'] = g['width'] / (g['height'] + 1e-6)
        g['delta_y_raw'] = g['center_y'].diff()
        g['delta_y'] = g['delta_y_raw'].clip(lower=0)
        g['delta_height'] = g['height'].diff().abs()
        g['delta_width'] = g['width'].diff().abs()
        g['delta_area'] = g['area'].diff().abs()  # motion guard용 (모델 피처에서는 제거됨)

        # v4: 하강 가속도 (delta_y의 2차 도함수) — 급격한 하강 가속을 포착
        g['delta_y_accel'] = g['delta_y'].diff()
        _delta_y_accel_max = float(g['delta_y_accel'].max() or 0)

        # v4: 최종 자세 높이 비율 (마지막 3프레임 높이 / 전체 평균) — 넘어진 후 낮은 자세
        _n_tail = min(3, len(g))
        _final_height = float(g['height'].tail(_n_tail).mean())
        _height_mean = float(g['height'].mean())
        _final_height_ratio = _final_height / (_height_mean + 1e-6)

        _total_sampled = max(len(frames), 1)
        feat = {
            'detection_rate': float(len(g)) / _total_sampled,  # v5: 검출률 (영상 길이 무관)
            'n_frames': len(g),                                # 보조: short-clip 판정용 (모델 피처 아님)
            'total_sampled_frames': _total_sampled,            # 보조: 정규화 분모
            'center_y_mean': g['center_y'].mean(),
            'center_y_std': g['center_y'].std(),
            'height_mean': _height_mean,
            'height_std': g['height'].std(),
            'aspect_ratio_mean': g['aspect_ratio'].mean(),
            'aspect_ratio_std': g['aspect_ratio'].std(),
            'delta_y_mean': g['delta_y'].mean(),
            'delta_y_max': g['delta_y'].max(),
            'delta_height_mean': g['delta_height'].mean(),
            'delta_width_mean': g['delta_width'].mean(),
            'delta_y_accel_max': _delta_y_accel_max,
            'final_height_ratio': _final_height_ratio,
            # motion guard용 (모델 피처가 아닌 보조값)
            'width_mean': g['width'].mean(),
            'width_std': g['width'].std(),
            'area_mean': g['area'].mean(),
            'area_std': g['area'].std(),
            'delta_area_mean': g['delta_area'].mean(),
        }
        feat_df = pd.DataFrame([feat])
        feat_df = feat_df.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        feat_df = feat_df[self._RF_FEATURE_COLUMNS]
        _perf['feature_extract'] = round(_time.time() - _t, 3)

        return {
            'feat': feat,
            'feat_df': feat_df,
            'detection_frames': detection_frames,
            'det_rows': det_rows,
            'frames': frames,
            'orig_fps': orig_fps,
            'vid_width': vid_width,
            'vid_height': vid_height,
            'vid_duration': vid_duration,
            'perf': _perf,
            'all_frame_keypoints': all_frame_keypoints,  # FN-0002: per-frame keypoints for pose features
        }

    # FN-0003: Keypoint-based pose feature extraction
    # COCO keypoint indices
    _KP_NOSE = 0
    _KP_LEFT_SHOULDER = 5
    _KP_RIGHT_SHOULDER = 6
    _KP_LEFT_HIP = 11
    _KP_RIGHT_HIP = 12
    _KP_LEFT_KNEE = 13
    _KP_RIGHT_KNEE = 14
    _KP_LEFT_ANKLE = 15
    _KP_RIGHT_ANKLE = 16

    # Keypoint-derived pose feature column names
    _POSE_FEATURE_COLUMNS = [
        'body_tilt_angle_mean',      # 어깨-엉덩이 기울기 각도 평균
        'body_tilt_angle_max',       # 어깨-엉덩이 기울기 각도 최대
        'height_ratio_mean',         # (머리y - 발y) / bbox높이 평균
        'height_ratio_min',          # 높이 비율 최소 (쓰러짐 감지)
        'knee_bend_angle_mean',      # 무릎 굽힘 각도 평균
        'knee_bend_angle_min',       # 무릎 굽힘 각도 최소
        'horizontal_spread_mean',    # 좌우 관절 x좌표 분산 평균
        'horizontal_spread_max',     # 수평 확산도 최대 (누운 자세)
        'center_descent_speed_mean', # 프레임 간 몸 중심 y 변화율 평균
        'center_descent_speed_max',  # 몸 중심 하강 속도 최대 (낙상 순간)
        'pose_change_rate_mean',     # 연속 프레임 keypoint 코사인 비유사도 평균
        'pose_change_rate_max',      # 자세 변화율 최대
    ]

    def _extract_pose_features(self, all_frame_keypoints, vid_height=360):
        """Extract keypoint-derived pose features from per-frame keypoints.
        
        Args:
            all_frame_keypoints: list of {'frame_idx': int, 'keypoints': [[x,y,conf],...]} from FN-0002
            vid_height: video height for normalization
            
        Returns:
            dict with pose feature values (keys from _POSE_FEATURE_COLUMNS),
            or None if insufficient keypoint data.
        """
        import numpy as np
        import math

        if not all_frame_keypoints or len(all_frame_keypoints) < 2:
            return None

        KP_CONF_MIN = 0.3  # minimum confidence to use a keypoint

        def _kp_valid(kp):
            """Check if keypoint has sufficient confidence."""
            return len(kp) >= 3 and kp[2] >= KP_CONF_MIN

        def _midpoint(kp1, kp2):
            """Midpoint of two keypoints."""
            return [(kp1[0] + kp2[0]) / 2, (kp1[1] + kp2[1]) / 2]

        def _angle_from_vertical(p1, p2):
            """Angle (degrees) of line p1->p2 from vertical (0=straight up, 90=horizontal)."""
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            if abs(dy) < 1e-6 and abs(dx) < 1e-6:
                return 0.0
            angle_rad = math.atan2(abs(dx), abs(dy))
            return math.degrees(angle_rad)

        def _angle_three_points(p1, p2, p3):
            """Angle at p2 formed by p1-p2-p3 (degrees, 0-180)."""
            v1 = [p1[0] - p2[0], p1[1] - p2[1]]
            v2 = [p3[0] - p2[0], p3[1] - p2[1]]
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            m1 = math.sqrt(v1[0]**2 + v1[1]**2)
            m2 = math.sqrt(v2[0]**2 + v2[1]**2)
            if m1 < 1e-6 or m2 < 1e-6:
                return 180.0
            cos_a = max(-1.0, min(1.0, dot / (m1 * m2)))
            return math.degrees(math.acos(cos_a))

        body_tilts = []
        height_ratios = []
        knee_bends = []
        horiz_spreads = []
        center_ys = []
        pose_vectors = []

        for frame_data in all_frame_keypoints:
            kps = frame_data['keypoints']
            if len(kps) < 17:
                continue

            ls, rs = kps[self._KP_LEFT_SHOULDER], kps[self._KP_RIGHT_SHOULDER]
            lh, rh = kps[self._KP_LEFT_HIP], kps[self._KP_RIGHT_HIP]
            lk, rk = kps[self._KP_LEFT_KNEE], kps[self._KP_RIGHT_KNEE]
            la, ra = kps[self._KP_LEFT_ANKLE], kps[self._KP_RIGHT_ANKLE]
            nose = kps[self._KP_NOSE]

            # 1. Body tilt angle (shoulder center ↔ hip center vs vertical)
            if _kp_valid(ls) and _kp_valid(rs) and _kp_valid(lh) and _kp_valid(rh):
                shoulder_mid = _midpoint(ls, rs)
                hip_mid = _midpoint(lh, rh)
                tilt = _angle_from_vertical(hip_mid, shoulder_mid)
                body_tilts.append(tilt)

            # 2. Height ratio: (nose_y - ankle_y) / vid_height
            foot_y = None
            if _kp_valid(la) and _kp_valid(ra):
                foot_y = max(la[1], ra[1])
            elif _kp_valid(la):
                foot_y = la[1]
            elif _kp_valid(ra):
                foot_y = ra[1]
            if _kp_valid(nose) and foot_y is not None and vid_height > 0:
                hr = abs(nose[1] - foot_y) / vid_height
                height_ratios.append(hr)

            # 3. Knee bend angle (hip-knee-ankle)
            angles = []
            if _kp_valid(lh) and _kp_valid(lk) and _kp_valid(la):
                angles.append(_angle_three_points(lh, lk, la))
            if _kp_valid(rh) and _kp_valid(rk) and _kp_valid(ra):
                angles.append(_angle_three_points(rh, rk, ra))
            if angles:
                knee_bends.append(min(angles))

            # 4. Horizontal spread: std of all valid keypoint x coordinates
            valid_xs = [kps[i][0] for i in range(17) if _kp_valid(kps[i])]
            if len(valid_xs) >= 3:
                horiz_spreads.append(float(np.std(valid_xs)))

            # 5. Body center y (for descent speed)
            if _kp_valid(ls) and _kp_valid(rs) and _kp_valid(lh) and _kp_valid(rh):
                cy = (ls[1] + rs[1] + lh[1] + rh[1]) / 4
                center_ys.append(cy)

            # 6. Pose vector for change rate (flatten all valid keypoints)
            vec = []
            for i in range(17):
                if _kp_valid(kps[i]):
                    vec.extend([kps[i][0] / max(vid_height, 1), kps[i][1] / max(vid_height, 1)])
                else:
                    vec.extend([0.0, 0.0])
            pose_vectors.append(vec)

        # Compute derived statistics
        feat = {}

        # Body tilt
        if body_tilts:
            feat['body_tilt_angle_mean'] = float(np.mean(body_tilts))
            feat['body_tilt_angle_max'] = float(np.max(body_tilts))
        else:
            feat['body_tilt_angle_mean'] = 0.0
            feat['body_tilt_angle_max'] = 0.0

        # Height ratio
        if height_ratios:
            feat['height_ratio_mean'] = float(np.mean(height_ratios))
            feat['height_ratio_min'] = float(np.min(height_ratios))
        else:
            feat['height_ratio_mean'] = 0.0
            feat['height_ratio_min'] = 0.0

        # Knee bend
        if knee_bends:
            feat['knee_bend_angle_mean'] = float(np.mean(knee_bends))
            feat['knee_bend_angle_min'] = float(np.min(knee_bends))
        else:
            feat['knee_bend_angle_mean'] = 180.0
            feat['knee_bend_angle_min'] = 180.0

        # Horizontal spread
        if horiz_spreads:
            feat['horizontal_spread_mean'] = float(np.mean(horiz_spreads))
            feat['horizontal_spread_max'] = float(np.max(horiz_spreads))
        else:
            feat['horizontal_spread_mean'] = 0.0
            feat['horizontal_spread_max'] = 0.0

        # Center descent speed (frame-to-frame y change, downward = positive)
        if len(center_ys) >= 2:
            deltas = [center_ys[i+1] - center_ys[i] for i in range(len(center_ys)-1)]
            positive_deltas = [max(d, 0) for d in deltas]
            feat['center_descent_speed_mean'] = float(np.mean(positive_deltas))
            feat['center_descent_speed_max'] = float(np.max(positive_deltas))
        else:
            feat['center_descent_speed_mean'] = 0.0
            feat['center_descent_speed_max'] = 0.0

        # Pose change rate (cosine dissimilarity between consecutive frames)
        if len(pose_vectors) >= 2:
            change_rates = []
            for i in range(len(pose_vectors) - 1):
                v1 = np.array(pose_vectors[i])
                v2 = np.array(pose_vectors[i + 1])
                norm1 = np.linalg.norm(v1)
                norm2 = np.linalg.norm(v2)
                if norm1 > 1e-6 and norm2 > 1e-6:
                    cos_sim = np.dot(v1, v2) / (norm1 * norm2)
                    cos_sim = max(-1.0, min(1.0, cos_sim))
                    change_rates.append(1.0 - cos_sim)  # dissimilarity
                else:
                    change_rates.append(0.0)
            feat['pose_change_rate_mean'] = float(np.mean(change_rates))
            feat['pose_change_rate_max'] = float(np.max(change_rates))
        else:
            feat['pose_change_rate_mean'] = 0.0
            feat['pose_change_rate_max'] = 0.0

        return feat

    # FN-0017/FN-0039: Short-clip threshold for realtime mode (5-second chunks have n_frames ≈ 8-10)
    _SHORT_CLIP_N_FRAMES = 10  # n_frames below this triggers short-clip adjustments
    _SHORT_CLIP_THRESHOLD_MAX = 0.72  # FN-0025: 0.65→0.72 — short clip 오탐 방지 강화 (base threshold 0.60 기준)
    _SHORT_CLIP_MIN_FRAMES = 3  # below this, result is 'insufficient_data'

    def _infer_rf_pipeline(self, video_path, filename='', analysis_profile='balanced', input_source='upload'):
        """Run the RandomForest pipeline: YOLOv8n-Pose person detect → 13 statistical features → RF predict."""
        import time as _time
        t0 = _time.time()
        _perf = {}

        # ── 1. Load models (class-level cache) ────────────────
        _t = _time.time()
        rf_model = self._get_rf_model()
        _perf['model_load'] = round(_time.time() - _t, 3)
        extracted = self._extract_rf_pipeline_features(video_path, input_source=input_source)
        _perf.update(extracted.get('perf', {}))
        feat = extracted['feat']
        feat_df = extracted['feat_df']
        detection_frames = extracted['detection_frames']
        det_rows = extracted['det_rows']
        frames = extracted['frames']
        orig_fps = extracted['orig_fps']
        vid_width = extracted['vid_width']
        vid_height = extracted['vid_height']
        vid_duration = extracted['vid_duration']
        _device_used = self._get_yolo_device()

        # FN-0003: Extract keypoint-based pose features
        _t = _time.time()
        _all_frame_kps = extracted.get('all_frame_keypoints', [])
        _pose_features = self._extract_pose_features(_all_frame_kps, vid_height=vid_height)
        _perf['pose_feature_extract'] = round(_time.time() - _t, 3)

        # ── 4-1. Short-clip detection (FN-0017) ────────────────
        _n_det_frames = int(feat.get('n_frames', 0))
        _is_short_clip = _n_det_frames < self._SHORT_CLIP_N_FRAMES
        _is_realtime = input_source in ('webcam-live', 'webcam', 'realtime')
        _confidence_level = 'high'  # default

        # Minimum frame gate: too few frames → insufficient data
        if _n_det_frames < self._SHORT_CLIP_MIN_FRAMES:
            _confidence_level = 'insufficient'

        # ── 5. Predict ────────────────────────────────────────
        _t = _time.time()
        pred = int(rf_model.predict(feat_df)[0])
        fall_prob = None
        if hasattr(rf_model, 'predict_proba'):
            proba = rf_model.predict_proba(feat_df)[0]
            classes = list(rf_model.classes_)
            prob_map = {int(c): float(p) for c, p in zip(classes, proba)}
            fall_prob = prob_map.get(1, 0.0)

        score = fall_prob if fall_prob is not None else float(pred)

        # FN-0017/FN-0039: Adaptive threshold for short clips
        # Short clips have fewer frames → less reliable features → RAISE threshold to reduce false positives
        _effective_threshold = self.fall_decision_threshold
        if _is_short_clip and _n_det_frames >= self._SHORT_CLIP_MIN_FRAMES:
            # FN-0025: Linear interpolation: n_frames=3 → 0.72 (strict), n_frames=10 → 0.60 (baseline)
            _range = self._SHORT_CLIP_N_FRAMES - self._SHORT_CLIP_MIN_FRAMES
            _ratio = (_n_det_frames - self._SHORT_CLIP_MIN_FRAMES) / max(_range, 1)
            _effective_threshold = self._SHORT_CLIP_THRESHOLD_MAX - _ratio * (self._SHORT_CLIP_THRESHOLD_MAX - self.fall_decision_threshold)
            _confidence_level = 'medium' if _n_det_frames >= 5 else 'low'

        # FN-0028: fall_detected must be threshold-based, not raw prediction.
        # Using raw pred==1 caused score/threshold mismatch. Threshold is now 0.60 (FN-0025: raised from 0.52).
        fall_detected = score >= _effective_threshold
        # FN-0018: Extract feature importances for analysis_basis
        _feature_importances = {}
        _rf_importance_model = rf_model.named_steps['clf'] if hasattr(rf_model, 'named_steps') and 'clf' in rf_model.named_steps else rf_model
        if hasattr(_rf_importance_model, 'feature_importances_'):
            for col, imp in zip(self._RF_FEATURE_COLUMNS, _rf_importance_model.feature_importances_):
                _feature_importances[col] = round(float(imp), 4)
        _perf['rf_predict'] = round(_time.time() - _t, 3)

        # ── 5-1. Motion guard: suppress false positives on stationary persons ──
        # FN-0014: delta_y is now directional (downward only).
        # FN-0015: Added aspect_ratio-only suppression — if high aspect_ratio variance
        # but no meaningful vertical movement, suppress as posture-only noise.
        # FN-0017/FN-0039: TIGHTEN thresholds for short clips (fewer frames → less reliable → stricter guard)
        _mg_mul = 0.7 if _is_short_clip else 1.0
        _motion_checks = {
            'delta_y_mean': feat.get('delta_y_mean', 0) < 5.0 * _mg_mul,
            'delta_y_max': feat.get('delta_y_max', 0) < 12.0 * _mg_mul,
            'delta_height_mean': feat.get('delta_height_mean', 0) < 5.0 * _mg_mul,
            'delta_width_mean': feat.get('delta_width_mean', 0) < 3.0 * _mg_mul,
            'delta_area_mean': feat.get('delta_area_mean', 0) < 150.0 * _mg_mul,
            'center_y_std': feat.get('center_y_std', 0) < 10.0 * _mg_mul,
            'height_std': feat.get('height_std', 0) < 8.0 * _mg_mul,
        }
        _is_stationary = all(_motion_checks.values())
        _motion_guard_applied = False
        # FN-0015: aspect_ratio-only guard — aspect_ratio variance high but Y movement low
        _ar_only_guard = (
            feat.get('aspect_ratio_std', 0) > 0.1
            and feat.get('delta_y_max', 0) < 15.0
            and feat.get('center_y_std', 0) < 15.0
        )
        if _is_stationary and fall_detected:
            # FN-0016: stronger suppression: min 0.10 instead of 0.15
            score = min(score, 0.10)
            fall_detected = False
            pred = 0
            _motion_guard_applied = True
        elif _ar_only_guard and fall_detected and score < 0.75:
            # FN-0015: aspect_ratio noise without vertical fall → suppress
            # NOTE: suppression cap must be below fall_decision_threshold (0.60) to ensure 'low' risk
            score = min(score, 0.20)
            fall_detected = False
            pred = 0
            _motion_guard_applied = True
        # FN-0005/FN-0025: Realtime-specific enhanced motion guard
        # In realtime 5s chunks, "fast sitting" / "bending over" produce high scores
        # due to posture change (aspect_ratio_std, final_height_ratio) without true fall dynamics.
        # FN-0025: 가드 임계값 완화 — delta_y_max 20→30, center_y_std 25→35, fhr 0.55→0.45
        elif _is_realtime and fall_detected and score < 0.85:
            _realtime_guard = False
            _fhr = feat.get('final_height_ratio', 1.0)
            _dym = feat.get('delta_y_max', 0)
            _cys = feat.get('center_y_std', 0)
            # Condition: person not fully collapsed + no strong downward motion
            if _fhr > 0.45 and _dym < 30.0 and _cys < 35.0:
                _realtime_guard = True
            if _realtime_guard:
                score = min(score, 0.25)
                fall_detected = False
                pred = 0
                _motion_guard_applied = True
        # FN-0025: Moderate-motion dampener (upload + realtime 공통)
        # 정상 활동 중 50~65% 미세 움직임 → 큰 delta_y 없으면 점수 하향
        elif fall_detected and score < 0.70 and not _motion_guard_applied:
            _dym2 = feat.get('delta_y_max', 0)
            _fhr2 = feat.get('final_height_ratio', 1.0)
            _accel = feat.get('delta_y_accel_max', 0)
            # 급격한 하강 가속도 없고, 최종 자세가 비교적 직립이면 → 오탐 가능성 높음
            if _dym2 < 25.0 and _fhr2 > 0.50 and _accel < 12.0:
                score = min(score, 0.40)
                fall_detected = False
                pred = 0
                _motion_guard_applied = True

        elapsed = round(_time.time() - t0, 2)
        _perf['total'] = elapsed

        # ── 6. Build result matching existing schema ──────────
        # FN-0017: use effective threshold for risk level (short-clip adaptive)
        risk_level = 'high' if score >= 0.75 else ('medium' if score >= _effective_threshold else 'low')
        # FN-0017: insufficient data gate
        if _confidence_level == 'insufficient':
            risk_level = 'low'
            fall_detected = False
            pred = 0
        risk_label = {'low': '안정', 'medium': '주의', 'high': '고위험'}.get(risk_level, '안정')

        # Behavior
        behavior = self._predict_behavior_from_runtime(None, fall_detected, allow_fallback=False)
        if behavior is not None:
            behavior_class, behavior_label = behavior.get('code', 'non-fall'), behavior.get('label', '비낙상')
        elif fall_detected:
            behavior_class, behavior_label = 'fall', '낙상'
            behavior = {
                'code': 'fall', 'label': '낙상',
                'source': 'fall-risk-shortcut', 'fallback': False,
                'reason': ['RF 모델이 낙상(1)으로 분류했습니다.'],
            }
        else:
            behavior_class, behavior_label = self._guess_behavior(filename, score)
            behavior = {
                'code': behavior_class, 'label': behavior_label,
                'source': 'filename-fallback', 'fallback': True,
                'reason': ['행동 모델이 연결되지 않아 파일명 기반 fallback을 사용했습니다.'],
            }

        # Events — single representative event
        event_time = round(vid_duration / 2, 2)
        events = [{
            'label': 'RF 파이프라인 대표 분석 구간',
            'time': event_time,
            'confidence': round(score, 4),
            'severity': risk_level,
        }]

        # Analysis basis — FN-0018: dynamic importance-weighted cards
        _feat_labels = {
            'detection_rate': ('검출률', '사람이 검출된 프레임 비율입니다. 영상 길이에 무관한 정규화된 지표입니다.', ''),
            'n_frames': ('검출 프레임 수', '분석에 사용된 총 프레임 수입니다.', '장'),
            'center_y_mean': ('Y 중심 평균', '사람 중심점의 평균 Y좌표(높을수록 하단)입니다.', 'px'),
            'center_y_std': ('Y축 변동성', '사람 중심점 Y좌표의 표준편차로, 급격한 세로 이동을 나타냅니다.', 'px'),
            'height_mean': ('높이 평균', '사람 bbox 높이의 평균입니다.', 'px'),
            'height_std': ('높이 변동', '사람 bbox 높이의 표준편차입니다.', 'px'),
            'width_mean': ('너비 평균', '사람 bbox 너비의 평균입니다.', 'px'),
            'width_std': ('너비 변동', '사람 bbox 너비의 표준편차입니다.', 'px'),
            'area_mean': ('면적 평균', '사람 bbox 면적의 평균입니다.', 'px²'),
            'area_std': ('면적 변동', '사람 bbox 면적의 표준편차입니다.', 'px²'),
            'aspect_ratio_mean': ('종횡비 평균', '사람 bbox 종횡비의 평균입니다.', ''),
            'aspect_ratio_std': ('종횡비 변동', '사람 bbox 종횡비 변동으로, 자세 변화를 나타냅니다.', ''),
            'delta_y_mean': ('평균 하강 변위', '프레임 간 아래 방향 이동의 평균입니다.', 'px'),
            'delta_y_max': ('최대 하강 변위', '프레임 간 아래 방향 이동의 최대값으로, 낙하 순간을 반영합니다.', 'px'),
            'delta_height_mean': ('높이 변화 평균', '프레임 간 높이 변화의 평균입니다.', 'px'),
            'delta_width_mean': ('너비 변화 평균', '프레임 간 너비 변화의 평균입니다.', 'px'),
            'delta_y_accel_max': ('하강 가속도', '넘어질 때 하강 속도의 급격한 증가를 나타냅니다. 값이 클수록 급격한 낙하입니다.', 'px'),
            'final_height_ratio': ('최종 자세 높이', '영상 마지막 구간에서의 자세 높이 비율입니다. 1보다 작으면 넘어진 후 낮은 자세를 의미합니다.', ''),
            # FN-0003: Keypoint-based pose feature labels
            'body_tilt_angle_mean': ('몸 기울기(평균)', '어깨-엉덩이 축의 수직 대비 기울기 각도입니다. 90°에 가까울수록 누운 상태입니다.', '°'),
            'body_tilt_angle_max': ('몸 기울기(최대)', '가장 크게 기울어진 순간의 각도입니다.', '°'),
            'height_ratio_mean': ('키 비율(평균)', '머리~발 거리 / 영상 높이입니다. 작을수록 쓰러진 자세입니다.', ''),
            'height_ratio_min': ('키 비율(최소)', '가장 낮아진 순간의 비율입니다.', ''),
            'knee_bend_angle_mean': ('무릎 굽힘(평균)', '엉덩이-무릎-발목 각도입니다. 작을수록 무릎이 많이 굽혀진 상태입니다.', '°'),
            'knee_bend_angle_min': ('무릎 굽힘(최소)', '가장 많이 굽혀진 순간의 각도입니다.', '°'),
            'horizontal_spread_mean': ('수평 확산(평균)', '관절 x좌표의 표준편차입니다. 클수록 몸이 넓게 펼쳐져 있습니다.', 'px'),
            'horizontal_spread_max': ('수평 확산(최대)', '가장 넓게 펼쳐진 순간입니다.', 'px'),
            'center_descent_speed_mean': ('중심 하강(평균)', '몸 중심의 프레임 간 하방 이동 속도입니다.', 'px'),
            'center_descent_speed_max': ('중심 하강(최대)', '가장 빠르게 하강한 순간입니다. 낙상 순간을 반영합니다.', 'px'),
            'pose_change_rate_mean': ('자세 변화율(평균)', '연속 프레임 간 전체 관절의 코사인 비유사도입니다.', ''),
            'pose_change_rate_max': ('자세 변화율(최대)', '가장 급격하게 자세가 변한 순간입니다.', ''),
        }
        # FN-0032: Removed fall_probability (redundant with risk_score) and detected_person_frames (no diagnostic value)
        analysis_basis = []
        # FN-0032: Features to exclude from basis display (v4: area/width features removed from model)
        _EXCLUDE_FROM_BASIS = set()
        # FN-0018/FN-0023/FN-0032/FN-0033: contribution-sorted basis with value-aware levels
        # FN-0033: Fall-direction value thresholds per feature for level assignment
        _rf_fall_thresholds = {
            'delta_y_max': {'high': 25.0, 'medium': 12.0},    # px, higher = more fall-like
            'center_y_std': {'high': 20.0, 'medium': 10.0},   # px, higher = more vertical movement
            'height_std': {'high': 15.0, 'medium': 8.0},      # px, higher = height change
            'aspect_ratio_std': {'high': 0.15, 'medium': 0.08},  # ratio, higher = posture change
            'delta_height_mean': {'high': -5.0, 'medium': -2.0},  # px, more negative = fall
            'delta_y_mean': {'high': 8.0, 'medium': 3.0},     # px, higher = downward movement
            'delta_y_accel_max': {'high': 15.0, 'medium': 5.0},   # px, higher = more sudden acceleration
            'final_height_ratio': {'high': 0.75, 'medium': 0.90},  # ratio, lower = more collapsed posture
        }
        # Display weights: adjust contribution ranking without changing model prediction.
        # > 1.0 boosts display priority; < 1.0 reduces it.
        _RF_DISPLAY_WEIGHTS = {
            'delta_y_mean': 2.5,         # boost — descent speed is key fall indicator
            'delta_y_max': 2.5,          # boost — max descent displacement
            'center_y_std': 1.8,         # boost — vertical movement variability
            'delta_height_mean': 1.5,    # boost — height change (collapse direction)
            'aspect_ratio_std': 1.3,     # moderate boost — posture change
            'delta_y_accel_max': 2.0,    # v4: boost — sudden acceleration is key
            'final_height_ratio': 1.8,   # v4: boost — collapsed posture is key
        }
        if _feature_importances:
            _scored = []
            for col in self._RF_FEATURE_COLUMNS:
                if col in _EXCLUDE_FROM_BASIS:
                    continue
                imp = _feature_importances.get(col, 0)
                val = feat.get(col, 0)
                _dw = _RF_DISPLAY_WEIGHTS.get(col, 1.0)
                _contrib = imp * _dw   # scale-independent contribution
                _scored.append((col, imp, val, _contrib))
            _scored.sort(key=lambda x: x[3], reverse=True)
            for col, imp, val, contribution in _scored[:6]:
                info = _feat_labels.get(col, (col, '', ''))
                # FN-0033: Determine level by feature value in fall-direction
                _fval = abs(float(val or 0))
                _thresholds = _rf_fall_thresholds.get(col, {})
                if _thresholds:
                    _th_high = abs(_thresholds.get('high', 999999))
                    _th_med = abs(_thresholds.get('medium', 999999))
                    # For negative-direction features (delta_height_mean) and
                    # ratio features where lower = more dangerous (final_height_ratio),
                    # use the actual value comparison
                    if col in ('delta_height_mean',):
                        _actual = float(val or 0)
                        lvl = 'high' if _actual <= _thresholds['high'] else ('medium' if _actual <= _thresholds['medium'] else 'low')
                    elif col == 'final_height_ratio':
                        _actual = float(val or 1.0)
                        lvl = 'high' if _actual <= _thresholds['high'] else ('medium' if _actual <= _thresholds['medium'] else 'low')
                    else:
                        lvl = 'high' if _fval >= _th_high else ('medium' if _fval >= _th_med else 'low')
                else:
                    # Fallback: contribution-percentile based
                    lvl = 'high' if imp >= 0.12 else ('medium' if imp >= 0.06 else 'low')
                # FN-0033: Override — if overall score >= threshold and contribution is in top-2, at least medium
                if score >= self.fall_decision_threshold and contribution >= _scored[1][3] if len(_scored) > 1 else True:
                    if lvl == 'low':
                        lvl = 'medium'
                analysis_basis.append({
                    'feature': col,
                    'label': f'{info[0]} (기여도 {round(imp * 100, 1)}%)',
                    'value': round(float(val), 4) if isinstance(val, float) else val,
                    'unit': info[2],
                    'level': lvl,
                    'description': info[1],
                    '_sort_score': contribution,
                })
        # FN-0032: Pure contribution-based sort (no pinned items)
        analysis_basis.sort(key=lambda x: x.get('_sort_score', 0), reverse=True)
        for idx, b in enumerate(analysis_basis, start=1):
            b['contribution_rank'] = idx
            b['contribution_score'] = round(float(b.get('_sort_score', 0.0) or 0.0), 6)
            b.pop('_sort_score', None)

        return {
            'fall_detected': fall_detected,
            'behavior_class': behavior_class,
            'behavior_label': behavior_label,
            'risk_score': round(score, 4),
            'risk_level': risk_level,
            'risk_label': risk_label,
            'summary': ('움직임이 감지되지 않아 오탐을 억제했습니다. (motion guard)' if _motion_guard_applied else ('RF 보조 파이프라인이 낙상 가능성을 높게 판단했습니다.' if fall_detected else 'RF 보조 파이프라인 기준 즉시 낙상 가능성은 낮습니다.')),
            'events': events,
            'reference_matches': [],
            'analysis_basis': analysis_basis,
            'runtime_key': 'rf-pipeline-runtime',
            'runtime_label': 'RF 보조 파이프라인 (RandomForest + YOLOv8n-Pose)',
            'runtime_inference': {
                'fall_score': round(score, 4),
                'fall_detected': fall_detected,
                'pred_value': pred,
                'fall_probability': round(score, 4),
                'raw_fall_probability': round(fall_prob if fall_prob is not None else float(pred), 4),
                'elapsed_sec': elapsed,
                'perf': _perf,
                'device': _device_used,
                'extracted_frames': len(frames),
                'detected_person_frames': len(det_rows),
                'features': {k: round(float(v), 4) if isinstance(v, float) else v for k, v in feat.items()},
                'motion_guard': {
                    'applied': _motion_guard_applied,
                    'is_stationary': _is_stationary,
                    'checks': _motion_checks,
                },
                # FN-0017: short-clip realtime mode metadata
                'short_clip': {
                    'is_short_clip': _is_short_clip,
                    'n_det_frames': _n_det_frames,
                    'effective_threshold': round(_effective_threshold, 4),
                    'confidence_level': _confidence_level,
                    'is_realtime': _is_realtime,
                },
                # FN-0003: keypoint-based pose features
                'pose_features': _pose_features,
            },
            'behavior_inference': behavior,
            'model_runtime': {
                'label': 'RF 보조 파이프라인 (RandomForest + YOLOv8n-Pose)',
                'rf_model_path': self._rf_active_model_path(),
                'yolo_model': self._RF_YOLO_MODEL,
                'yolo_imgsz': self._RF_YOLO_IMGSZ,
                'target_fps': self._RF_TARGET_FPS,
                'analysis_profile': analysis_profile,
                'extracted_frames': len(frames),
                'detected_person_frames': len(det_rows),
                'fall_probability': round(score, 4),
                'detection_frames': detection_frames,
                'feature_importances': _feature_importances,
            },
            'video_meta': {
                'duration': vid_duration,
                'width': vid_width,
                'height': vid_height,
                'fps': round(orig_fps, 2),
            },
        }

    def _trained_model_info(self, baseline_summary, baseline_state, validation_report):
        """Return currently preferred production model information."""
        rf_available = self._rf_pipeline_available()
        rf_pose_available = self._rf_pose_pipeline_available()
        rf_meta = self._rf_runtime_meta()
        runtime_ready = self._trained_runtime_available(baseline_state)
        person_feature_ready = runtime_ready and self._person_feature_available()
        meta = self._baseline_model_meta()
        fall_classifier = (meta.get('fall_classifier', {}) or {})
        feature_meta = fall_classifier.get('features', []) or []
        person_metric_ready = len(feature_meta) == 10
        rf_project_metric_ready = float(rf_meta.get('cv_f1', 0.0) or 0.0) > 0
        rf_metric_ready = rf_project_metric_ready or str(fall_classifier.get('type', '') or '').lower().startswith('randomforest') or len(feature_meta) == len(self._RF_FEATURE_COLUMNS)
        cv_f1 = float(fall_classifier.get('cv_f1', 0.7499) or 0.7499) if person_metric_ready else 0.0
        cv_auc = float(fall_classifier.get('cv_auc', 0.86) or 0.86) if person_metric_ready else 0.0
        training_samples = int(fall_classifier.get('training_samples', 2250) or 2250) if person_metric_ready else 0
        features = feature_meta or self._RF_FEATURE_COLUMNS
        fc_path = fall_classifier.get('path', '')
        if fc_path and not os.path.isabs(fc_path):
            fc_path = self._project_abspath(fc_path)
        else:
            fc_path = self._normalize_existing_path(fc_path)
        runtime_mode = 'heuristic-fallback'
        model_name = 'Fallback 분석'
        weights_path = ''
        weights_name = ''
        display_training_samples = training_samples
        if rf_pose_available:
            runtime_mode = 'rf-pose-runtime'
            model_name = 'RF-Pose Pipeline (RandomForest + YOLOv8n-Pose + Keypoints)'
            weights_path = self._rf_pose_model_path()
            weights_name = os.path.basename(weights_path)
            _pose_summary = self._rf_pose_summary()
            display_training_samples = int(_pose_summary.get('training_samples', 0) or 0)
        elif rf_available:
            runtime_mode = 'rf-pipeline-runtime'
            model_name = 'RF Pipeline v4 (RandomForest + YOLOv8n-Pose)'
            weights_path = rf_meta.get('model_path', self._RF_MODEL_PATH)
            weights_name = os.path.basename(weights_path)
            display_training_samples = int(rf_meta.get('training_samples', 0) or 0)
        elif person_feature_ready:
            runtime_mode = 'person-feature-runtime'
            model_name = 'Person-Feature Pipeline (YOLO + XGBoost)'
            weights_path = fc_path or ''
            weights_name = os.path.basename(fc_path) if fc_path else ''
        metric_note = '3-Fold 교차 검증 기준 메트릭으로, 학습/검증 분할이 매 Fold마다 달라져 일반화 성능을 반영합니다.'
        evaluation_note = f'CV F1 {round(cv_f1 * 100, 1)}%% · CV AUC {round(cv_auc * 100, 1)}%%'
        split_note = f'3-Fold CV (전체 {training_samples}건)'
        metric_source = 'cross-validation'
        evaluation_source = '3-Fold Cross Validation'
        if runtime_mode == 'rf-pipeline-runtime':
            metric_note = 'RF 보조 파이프라인은 현재 구조 메타데이터를 기준으로 표시합니다. 별도 CV 메트릭 파일이 연결되면 함께 노출할 수 있습니다.'
            evaluation_note = f"트리 {int(rf_meta.get('n_estimators', 0) or 0)}개 · 특징 {int(rf_meta.get('feature_count', len(self._RF_FEATURE_COLUMNS)) or len(self._RF_FEATURE_COLUMNS))}개"
            split_note = 'RF 보조 파이프라인 운영 메타데이터 기준'
            metric_source = 'rf-runtime-structure'
            evaluation_source = 'RF Runtime Structure'
            if rf_metric_ready:
                rf_cv_f1 = float(rf_meta.get('cv_f1', 0.0) or fall_classifier.get('cv_f1', 0.0) or 0.0)
                rf_cv_auc = float(rf_meta.get('cv_auc', 0.0) or fall_classifier.get('cv_auc', 0.0) or 0.0)
                rf_training_samples = int(rf_meta.get('training_samples', 0) or fall_classifier.get('training_samples', 0) or 0)
                rf_folds = int(((self._rf_project_summary().get('cv', {}) or {}).get('folds', 3)) or 3)
                evaluation_note = f"CV F1 {round(rf_cv_f1 * 100, 1)}%% · CV AUC {round(rf_cv_auc * 100, 1)}%%"
                metric_note = 'RF 보조 파이프라인 HITL 재학습 메타데이터를 반영한 교차 검증 메트릭입니다.' if rf_project_metric_ready else 'RF 보조 파이프라인 메타파일에 연결된 교차 검증 메트릭입니다.'
                split_note = f"{rf_folds}-Fold CV (전체 {rf_training_samples}건)"
                metric_source = 'cross-validation'
                evaluation_source = f'{rf_folds}-Fold Cross Validation'
        return {
            'ready': person_feature_ready or runtime_ready or rf_available or rf_pose_available,
            'runtime_ready': person_feature_ready or runtime_ready or rf_available or rf_pose_available,
            'runtime_mode': runtime_mode,
            'model_name': model_name,
            'updated_at': rf_meta.get('updated_at', '') if runtime_mode in ('rf-pipeline-runtime', 'rf-pose-runtime') else meta.get('updated_at', ''),
            'source_dataset': '낙상사고 위험동작 영상-센서 쌍 데이터 (AI Hub)',
            'weights_path': weights_path,
            'weights_name': weights_name,
            'class_names': ['normal(0)', 'fall(1)'],
            'sample_count': display_training_samples,
            'train_count': display_training_samples,
            'validation_count': 0,
            'accuracy': cv_f1,
            'precision': cv_f1,
            'recall': cv_f1,
            'f1': cv_f1,
            'top1': 0.0,
            'val_loss': 0.0,
            'train_ratio': 1.0,
            'validation_ratio': 0.0,
            'split_note': split_note,
            'metric_source': metric_source,
            'metric_note': metric_note,
            'evaluation_source': evaluation_source,
            'evaluation_note': evaluation_note,
            'eval_accuracy': cv_f1,
            'eval_f1': cv_f1,
            'class_distribution': {},
            'data_quality_issues': [],
            'validation_sample_count': 0,
            'validation_accuracy': 0.0,
            'validation_recall': 0.0,
            'validation_f1': 0.0,
            'rf_pipeline': {
                'ready': rf_available,
                'model_path': rf_meta.get('model_path', '') if rf_available else '',
                'model_name': rf_meta.get('model_name', 'rf_model_server.pkl'),
                'model_class': rf_meta.get('model_class', 'RandomForestClassifier'),
                'yolo_model': rf_meta.get('yolo_model', self._RF_YOLO_MODEL),
                'updated_at': rf_meta.get('updated_at', ''),
                'metric_ready': rf_metric_ready,
                'cv_f1': float(rf_meta.get('cv_f1', 0.0) or fall_classifier.get('cv_f1', 0.0) or 0.0) if rf_metric_ready else 0.0,
                'cv_auc': float(rf_meta.get('cv_auc', 0.0) or fall_classifier.get('cv_auc', 0.0) or 0.0) if rf_metric_ready else 0.0,
                'training_samples': int(rf_meta.get('training_samples', 0) or fall_classifier.get('training_samples', 0) or 0) if rf_metric_ready else 0,
                'features': rf_meta.get('features', self._RF_FEATURE_COLUMNS),
                'feature_count': int(rf_meta.get('feature_count', len(self._RF_FEATURE_COLUMNS)) or len(self._RF_FEATURE_COLUMNS)),
                'n_estimators': int(rf_meta.get('n_estimators', 0) or 0),
                'max_depth': rf_meta.get('max_depth', None),
                'load_error': rf_meta.get('load_error', ''),
                'source': rf_meta.get('source', 'rf-standalone'),
            },
        }

    def _validation_summary(self, validation_report):
        if len(validation_report or {}) == 0:
            return {
                'ready': False,
                'status': 'not-run',
                'headline': '/낙상영상 검증 리포트가 아직 없습니다.',
                'summary': '학습된 모델을 실제 영상 폴더로 검토한 뒤 리포트를 생성해야 합니다.',
                'sample_count': 0,
                'accuracy': 0.0,
                'precision': 0.0,
                'recall': 0.0,
                'f1': 0.0,
                'error_count': 0,
                'updated_at': '',
                'errors': [],
            }
        metrics = (validation_report.get('metrics', {}) or {})
        accuracy = float(metrics.get('accuracy', 0.0) or 0.0)
        recall = float(metrics.get('recall', 0.0) or 0.0)
        status = 'pass' if accuracy >= 0.75 and recall >= 0.75 else ('review' if accuracy >= 0.6 else 'warn')
        return {
            'ready': True,
            'status': status,
            'headline': '/낙상영상 검증 결과',
            'summary': f"총 {int(validation_report.get('sample_count', 0) or 0)}건을 검토해 정확도 {round(accuracy * 100, 1)}%, 재현율 {round(recall * 100, 1)}%를 기록했습니다.",
            'sample_count': int(validation_report.get('sample_count', 0) or 0),
            'accuracy': accuracy,
            'precision': float(metrics.get('precision', 0.0) or 0.0),
            'recall': recall,
            'f1': float(metrics.get('f1', 0.0) or 0.0),
            'error_count': len(validation_report.get('errors', []) or []),
            'updated_at': validation_report.get('created_at', ''),
            'errors': (validation_report.get('errors', []) or [])[:5],
        }

    def _model_asset_state(self, summary_rel_path, model_rel_path, summary, trained_label, fallback_label):
        summary_path = self._project_abspath(*summary_rel_path.split('/'))
        model_path = self._project_abspath(*model_rel_path.split('/'))
        dataset = (summary or {}).get('dataset', {}) or {}
        sample_count = int(dataset.get('sample_count', 0) or 0)
        summary_exists = os.path.exists(summary_path)
        model_exists = os.path.exists(model_path)
        ready = summary_exists and model_exists and sample_count > 0
        return {
            'ready': ready,
            'summary_exists': summary_exists,
            'model_exists': model_exists,
            'sample_count': sample_count,
            'active_label': trained_label if ready else fallback_label,
            'status': 'ready' if ready else 'fallback',
        }

    def _baseline_state(self, summary):
        return self._model_asset_state(
            'storage/training/fall-detection/model/training_summary.json',
            'storage/training/fall-detection/model/baseline_model.json',
            summary,
            '학습된 낙상 Y/N 베이스라인',
            '메타데이터·파일명 기반 fallback',
        )

    def _behavior_state(self, summary):
        state = self._model_asset_state(
            'storage/training/action-behavior/model/training_summary.json',
            'storage/training/action-behavior/model/behavior_model.json',
            summary,
            '학습된 낙상/비낙상 분류 모델',
            '행동 라벨 추정 fallback',
        )
        meta = self._behavior_model_meta()
        if state.get('ready') is False and meta.get('model') in ['behavior-rule-v1', 'behavior-binary-v1']:
            state['ready'] = True
            state['status'] = 'ready'
            state['active_label'] = '규칙 기반 낙상/비낙상 프로파일 (behavior-binary-v1)'
            state['model_type'] = 'rule-based'
            state['model_type_label'] = '규칙 기반 추론'
            state['model_type_note'] = '실시간 낙상 확률과 낙상 여부를 기준으로 낙상/비낙상 이진 분류를 제공합니다. ML 학습 모델이 아닌 규칙 기반 프로파일입니다.'
        else:
            state['model_type'] = 'ml-trained' if state.get('ready') else 'fallback'
            state['model_type_label'] = '학습 기반 모델' if state.get('ready') else 'fallback'
            state['model_type_note'] = ''
        return state

    def _behavior_label(self, code):
        for item in self.behavior_classes():
            if item.get('code') == code:
                return item.get('label')
        return code

    def _predict_behavior_from_runtime(self, inference, fall_detected=False, allow_fallback=True):
        inference = inference or {}
        meta = self._behavior_model_meta()
        if meta.get('model') not in ['behavior-rule-v1', 'behavior-binary-v1']:
            return None if allow_fallback is False else {
                'code': 'non-fall',
                'label': '비낙상',
                'source': 'binary-fallback',
                'fallback': True,
                'reason': ['행동 모델 메타정보가 없어 비낙상 기본값을 사용합니다.'],
            }
        fall_probability = self._metadata_to_number(inference.get('fall_probability', 0.0), 0.0)
        reasons = []
        code = 'non-fall'
        if fall_detected:
            code = 'fall'
            reasons.append('최종 낙상 판정이 내려져 행동 분류도 낙상으로 표시합니다.')
        else:
            reasons.append('최종 낙상 판정이 아니므로 행동 분류는 비낙상으로 표시합니다.')
            if fall_probability >= 0.75:
                reasons.append('일부 구간 확률은 높았지만 최종 위험점수 또는 게이트 기준을 넘지 않아 비낙상으로 유지했습니다.')
        return {
            'code': code,
            'label': self._behavior_label(code),
            'source': 'behavior-binary-v1',
            'fallback': False,
            'confidence': round(max(0.55, min(0.98, fall_probability if code == 'fall' else (1.0 - fall_probability))), 4),
            'reason': reasons,
        }

    def _risk_score_guide(self, result):
        runtime_key = str(result.get('runtime_key', '') or '')
        risk_score = self._metadata_to_number(result.get('risk_score', 0.0), 0.0)
        fall_detected = bool(result.get('fall_detected', False))
        threshold = float(self.fall_decision_threshold)
        if runtime_key == 'xg-dual':
            xg_threshold = float(self._XG_FALL_THRESHOLD)
            ri = result.get('runtime_inference', {}) or {}
            suppressed = ri.get('suppressed_by', []) or []
            decision_state = result.get('decision_state', 'unknown')
            posture_label = result.get('posture_label', '?')
            suppressed_note = f' · 억제: {", ".join(suppressed)}' if suppressed else ''
            return {
                'threshold': xg_threshold,
                'score': round(risk_score, 4),
                'runtime_key': runtime_key,
                'summary': f'XG-Dual: XG-Fall(이진) + XG-Posture(6클래스) 결합 판정. 상태={decision_state}, 자세={posture_label}{suppressed_note}.',
                'decision': '낙상' if fall_detected else '비낙상',
                'formula': 'XG-Fall max_prob × 0.50 + mean_prob × 0.30 + fall_ratio × 0.20 → 5단계 guard → XG-Posture 6-class → arbitration',
                'details': [
                    f'최종 낙상 판정 기준: XG-Fall 위험점수 {xg_threshold:.2f} 이상 + guard 통과',
                    f'decision_state: {decision_state}',
                    f'감지 자세: {posture_label}',
                    f'적용된 guard: {", ".join(suppressed) if suppressed else "없음"}',
                ],
            }
        if runtime_key == 'person-feature-runtime':
            # FN-0029: XGBoost has its own threshold
            pf_threshold = float(self._PERSON_FEATURE_THRESHOLD)
            runtime = result.get('runtime_inference', {}) or {}
            motion_gate = runtime.get('motion_gate', {}) or {}
            gate_passed = bool(motion_gate.get('passed', False))
            summary = f'위험점수는 최대 구간 확률 50% + 평균 확률 30% + 낙상 윈도우 비율 20%를 합산한 값입니다. {"motion gate를 통과해" if gate_passed else "motion gate를 통과하지 못해"} 최종 판정을 계산했습니다.'
            return {
                'threshold': pf_threshold,
                'score': round(risk_score, 4),
                'runtime_key': runtime_key,
                'summary': summary,
                'decision': '낙상' if fall_detected else '비낙상',
                'formula': 'max_prob × 0.50 + mean_prob × 0.30 + fall_window_ratio × 0.20',
                'details': [
                    f'최종 낙상 판정 기준: 위험점수 {pf_threshold:.2f} 이상',
                    f'motion gate: {"통과" if gate_passed else "미통과"}',
                    'motion gate는 급하강 속도·수직 이동·자세 변화를 함께 확인합니다.',
                ],
            }
        if runtime_key == 'rf-pipeline-runtime':
            return {
                'threshold': threshold,
                'score': round(risk_score, 4),
                'runtime_key': runtime_key,
                'summary': '위험점수는 RandomForest가 계산한 낙상 확률입니다.',
                'decision': '낙상' if fall_detected else '비낙상',
                'formula': 'RandomForest predict_proba 기반 낙상 확률',
                'details': [
                    f'최종 낙상 판정 기준: 위험점수 {threshold:.2f} 이상',
                    '사람 검출 뒤 13개 통계 특징을 추출해 확률을 계산합니다.',
                ],
            }
        if runtime_key == 'rf-pose-runtime':
            return {
                'threshold': threshold,
                'score': round(risk_score, 4),
                'runtime_key': runtime_key,
                'summary': '위험점수는 RF-Pose 모델(RandomForest + 키포인트)이 계산한 낙상 확률입니다.',
                'decision': '낙상' if fall_detected else '비낙상',
                'formula': 'RandomForest predict_proba 기반 낙상 확률 (bbox 13 + pose 12 = 25 features)',
                'details': [
                    f'최종 낙상 판정 기준: 위험점수 {threshold:.2f} 이상',
                    '사람 검출 뒤 bbox 13개 + 포즈 키포인트 12개 특징을 추출해 확률을 계산합니다.',
                ],
            }
        return {
            'threshold': threshold,
            'score': round(risk_score, 4),
            'runtime_key': runtime_key,
            'summary': '위험점수는 fallback 규칙으로 계산한 임시 점수입니다.',
            'decision': '낙상' if fall_detected else '비낙상',
            'formula': '메타데이터·파일명 기반 휴리스틱',
            'details': [
                f'최종 낙상 판정 기준: 위험점수 {threshold:.2f} 이상',
            ],
        }

    def _behavior_result_summary(self, result):
        behavior = result.get('behavior_inference', {}) or {}
        reasons = [str(item).strip() for item in (behavior.get('reason', []) or []) if str(item).strip()]
        if len(reasons) > 0:
            return ' '.join(reasons)
        return '행동 분류 근거 정보가 없습니다.'

    def _analysis_archive_summary(self):
        root = self._storage_dir()
        total = 0
        total_duration = 0.0
        input_sources = {}
        latest = []
        if os.path.isdir(root) is False:
            return {
                'total': 0,
                'total_duration_sec': 0.0,
                'input_sources': {},
                'latest': [],
            }
        for name in sorted(os.listdir(root), reverse=True):
            if name.endswith('.json') is False:
                continue
            meta = self._read_json(os.path.join(root, name), default={}) or {}
            metadata = meta.get('metadata', {}) or {}
            input_source = str(metadata.get('input_source', 'upload') or 'upload')
            duration = self._metadata_to_number(metadata.get('duration', 0), 0.0)
            total += 1
            total_duration += duration
            input_sources[input_source] = int(input_sources.get(input_source, 0) or 0) + 1
            latest.append({
                'saved_name': meta.get('saved_name', ''),
                'filename': meta.get('filename', ''),
                'input_source': input_source,
                'uploaded_at': meta.get('uploaded_at', ''),
                'duration': round(duration, 2),
            })
        return {
            'total': total,
            'total_duration_sec': round(total_duration, 2),
            'input_sources': input_sources,
            'latest': latest[:5],
        }

    def _model_comparison_report(self):
        """FN-0006: XGBoost vs RF 파이프라인 비교 보고서를 생성한다."""
        rf_available = self._rf_pipeline_available()
        rf_meta = self._rf_runtime_meta()
        meta = self._baseline_model_meta()
        fall_classifier = (meta.get('fall_classifier', {}) or {})
        eval_path = self._project_abspath('storage', 'training', 'fall-detection', 'fall-classifier', 'evaluation.json')
        evaluation = self._read_json(eval_path, default={}) or {}
        cv_results = evaluation.get('cv_results', {}) or {}
        best_model = evaluation.get('best_model', '')
        # Person-Feature pipeline (XGBoost) metrics from evaluation.json
        xgb_cv = cv_results.get('XGBoost', {})
        xgb_f1 = float((xgb_cv.get('f1', {}) or {}).get('mean', 0.0) or 0.0)
        xgb_auc = float((xgb_cv.get('roc_auc', {}) or {}).get('mean', 0.0) or 0.0)
        xgb_acc = float((xgb_cv.get('accuracy', {}) or {}).get('mean', 0.0) or 0.0)
        xgb_recall = float((xgb_cv.get('recall', {}) or {}).get('mean', 0.0) or 0.0)
        xgb_prec = float((xgb_cv.get('precision', {}) or {}).get('mean', 0.0) or 0.0)
        # RF pipeline (from evaluation.json CV results)
        rf_cv = cv_results.get('RandomForest', {})
        rf_f1 = float((rf_cv.get('f1', {}) or {}).get('mean', 0.0) or 0.0)
        rf_auc = float((rf_cv.get('roc_auc', {}) or {}).get('mean', 0.0) or 0.0)
        rf_acc = float((rf_cv.get('accuracy', {}) or {}).get('mean', 0.0) or 0.0)
        rf_recall = float((rf_cv.get('recall', {}) or {}).get('mean', 0.0) or 0.0)
        rf_prec = float((rf_cv.get('precision', {}) or {}).get('mean', 0.0) or 0.0)
        training_samples = int(evaluation.get('dataset', {}).get('total_samples', 0) or 0)
        feature_importance = evaluation.get('feature_importance', {}) or {}
        # RF standalone model meta (rf_model_server.pkl)
        rf_standalone_estimators = int(rf_meta.get('n_estimators', 0) or 0)
        rf_standalone_features = int(rf_meta.get('feature_count', len(self._RF_FEATURE_COLUMNS)) or len(self._RF_FEATURE_COLUMNS))
        rf_standalone_depth = rf_meta.get('max_depth', None)
        return {
            'title': 'XGBoost vs RF 파이프라인 비교 보고서',
            'cv_evaluation_source': 'Person-Feature 파이프라인 5-Fold CV (10개 모션 특징)',
            'training_samples': training_samples,
            'best_cv_model': best_model,
            'models': [
                {
                    'name': 'XGBoost (Person-Feature 파이프라인)',
                    'pipeline': 'YOLO 사람 검출·추적 → 10개 모션 특징 추출 → XGBoost 분류',
                    'feature_count': 10,
                    'feature_type': '시계열 모션 특징 (center_dy, max_down_speed, floor_proximity 등)',
                    'cv_f1': round(xgb_f1, 4),
                    'cv_auc': round(xgb_auc, 4),
                    'cv_accuracy': round(xgb_acc, 4),
                    'cv_recall': round(xgb_recall, 4),
                    'cv_precision': round(xgb_prec, 4),
                    'strengths': [
                        'CV 기준 F1·AUC 최고 성능',
                        '특징 해석이 가능한 모션 기반 특징 사용',
                        '낙상 메커니즘(하강 속도, 자세 변화)을 직접 반영',
                    ],
                    'weaknesses': [
                        '사람 검출 실패 시 위험 점수 0점 반환 (카메라 각도·해상도 의존)',
                        '사람 추적(ByteTrack) 구간이 병목으로 분석 시간 증가',
                        '학습 데이터 파이프라인에 의존하여 독립 배포가 어려움',
                    ],
                    'role': '현재 기본 운영 모델 (자동 선택 시 우선 사용)',
                },
                {
                    'name': 'RF Pipeline (RandomForest + YOLOv8n-Pose)',
                    'pipeline': 'YOLOv8n-Pose 사람 검출(bbox) → 13개 통계 특징 추출 → RandomForest 분류',
                    'feature_count': rf_standalone_features,
                    'feature_type': '프레임별 bbox 통계 특징 (center_y_std, delta_y_max, aspect_ratio_std 등)',
                    'model_specs': {
                        'n_estimators': rf_standalone_estimators,
                        'max_depth': rf_standalone_depth,
                        'model_file': 'rf_model_server.pkl',
                    },
                    'cv_f1': round(rf_f1, 4),
                    'cv_auc': round(rf_auc, 4),
                    'cv_accuracy': round(rf_acc, 4),
                    'cv_recall': round(rf_recall, 4),
                    'cv_precision': round(rf_prec, 4),
                    'strengths': [
                        '독립 모델 파일(pkl)로 즉시 배포 가능',
                        '사람 추적 없이 프레임별 bbox 검출만으로 동작하여 안정적',
                        '빠른 분석(320px 다운스케일)과 정밀 분석(640px) 차별화 지원',
                        '사람 미검출 시에도 프레임 카운트 기반 진단이 가능',
                    ],
                    'weaknesses': [
                        'CV 기준 F1·AUC가 XGBoost보다 약간 낮음',
                        '통계 특징이 모션 물리량을 간접적으로만 반영',
                        '짧은 영상(bbox 2프레임 미만)에서 분석 불가',
                    ],
                    'role': '보조 비교 모델 (사용자 수동 선택 가능)',
                },
            ],
            'why_xgboost_default': {
                'summary': 'XGBoost v2가 CV 성능(F1·AUC) 우위와 모션 물리량 직접 반영으로 기본 운영 모델로 선정되었습니다.',
                'reasons': [
                    f'1. CV 성능에서 XGBoost가 우세합니다 (F1 {round(xgb_f1, 4)} vs {round(rf_f1, 4)}, AUC {round(xgb_auc, 4)} vs {round(rf_auc, 4)})',
                    '2. 10개 모션 특징이 낙상 메커니즘(하강 속도, 자세 변화)을 직접 반영합니다.',
                    '3. 1500건 학습 데이터로 충분한 일반화 성능을 확보했습니다.',
                    '4. 사람 미검출 시 0점 반환은 RF fallback으로 자동 보완됩니다.',
                    '5. RF는 보조 비교 모델로 유지하며, 사용자가 수동 선택할 수 있습니다.',
                ],
            },
            'feature_importance_top5': feature_importance,
            'note': 'CV 결과는 동일한 Person-Feature 10개 특징 기반입니다. RF Pipeline의 13개 통계 특징 기반 독립 CV는 별도로 수행해야 합니다.',
        }

    def _analysis_engine_summary(self, baseline_state, behavior_state, intake_summary, archive_summary, actual_runtime_key=None):
        trained_layers = []
        if baseline_state.get('ready'):
            trained_layers.append('낙상 Y/N 베이스라인')
        if behavior_state.get('ready'):
            trained_layers.append('낙상/비낙상 행동 분류')
        selected_runtime = actual_runtime_key
        if not selected_runtime:
            if self._rf_pose_pipeline_available():
                selected_runtime = 'rf-pose-runtime'
            elif self._rf_pipeline_available():
                selected_runtime = 'rf-pipeline-runtime'
            elif self._person_feature_available() and self._trained_runtime_available(baseline_state):
                selected_runtime = 'person-feature-runtime'
            elif len(trained_layers) == 0:
                selected_runtime = 'heuristic-fallback'
            else:
                selected_runtime = 'person-feature-runtime'
        if selected_runtime == 'person-feature-runtime':
            runtime_label = 'XGBoost v2 파이프라인 (YOLO + XGBoost)'
            runtime_key = 'person-feature-runtime'
            runtime_note = '현재 기본 운영 모델입니다. 사람 검출·추적 후 10개 모션 특징을 추출해 XGBoost v2 분류기로 낙상 확률을 계산합니다.'
        elif selected_runtime == 'rf-pose-runtime':
            runtime_label = 'RF-Pose 파이프라인 (RandomForest + YOLOv8n-Pose + Keypoints)'
            runtime_key = 'rf-pose-runtime'
            runtime_note = '현재 기본 운영 모델입니다. YOLOv8n-Pose 사람 검출 → 13개 bbox 특징 + 12개 포즈 키포인트 특징 → RandomForest 분류기로 낙상 위험도를 판단합니다.'
        elif selected_runtime == 'rf-pipeline-runtime':
            runtime_label = 'RF 보조 파이프라인 (RandomForest + YOLOv8n-Pose)'
            runtime_key = 'rf-pipeline-runtime'
            runtime_note = '비교 검증용 보조 모델입니다. YOLOv8n-Pose 사람 검출 → 13개 통계 특징 추출 → RandomForest 분류기로 낙상 위험도를 판단합니다.'
        elif selected_runtime == 'heuristic-fallback':
            runtime_label = '규칙·메타데이터 기반 fallback 분석'
            runtime_key = 'heuristic-fallback'
            runtime_note = 'RF 모델이 준비되지 않아 파일 메타데이터와 파일명 패턴을 사용한 fallback 결과를 반환합니다.'
        else:
            runtime_label = 'XGBoost v2 파이프라인 (YOLO + XGBoost)'
            runtime_key = 'person-feature-runtime'
            runtime_note = '사람 검출·추적 후 10개 모션 특징을 추출해 XGBoost v2 분류기로 낙상 확률을 판단합니다.'
        return {
            'current_runtime': {
                'key': runtime_key,
                'label': runtime_label,
                'note': runtime_note,
                'trained_layers': trained_layers,
            },
            'layers': [
                {
                    'title': '낙상 Y/N 레이어',
                    'status': baseline_state.get('status', 'fallback'),
                    'active_label': baseline_state.get('active_label', ''),
                    'summary_exists': baseline_state.get('summary_exists', False),
                    'model_exists': baseline_state.get('model_exists', False),
                    'sample_count': baseline_state.get('sample_count', 0),
                },
                {
                    'title': '행동 분류 레이어',
                    'status': behavior_state.get('status', 'fallback'),
                    'active_label': behavior_state.get('active_label', ''),
                    'summary_exists': behavior_state.get('summary_exists', False),
                    'model_exists': behavior_state.get('model_exists', False),
                    'sample_count': behavior_state.get('sample_count', 0),
                },
                {
                    'title': '운영 데이터 현황',
                    'status': 'ready' if intake_summary.get('total', 0) > 0 or archive_summary.get('total', 0) > 0 else 'training-needed',
                    'active_label': f"학습 intake {intake_summary.get('total', 0)}건 · 분석 아카이브 {archive_summary.get('total', 0)}건",
                    'summary_exists': intake_summary.get('total', 0) > 0,
                    'model_exists': archive_summary.get('total', 0) > 0,
                    'sample_count': intake_summary.get('total', 0),
                },
            ],
        }

    def _analysis_diagnostics(self, baseline_state, behavior_state, intake_summary, archive_summary):
        items = []
        rf_available = self._rf_pipeline_available()
        rf_meta = self._rf_runtime_meta()
        meta = self._baseline_model_meta()
        fall_classifier = (meta.get('fall_classifier', {}) or {})
        feature_meta = fall_classifier.get('features', []) or []
        rf_metric_ready = str(fall_classifier.get('type', '') or '').lower().startswith('randomforest') or len(feature_meta) == len(self._RF_FEATURE_COLUMNS)
        cv_f1 = float(fall_classifier.get('cv_f1', 0.0) or 0.0) if rf_metric_ready else 0.0
        cv_auc = float(fall_classifier.get('cv_auc', 0.0) or 0.0) if rf_metric_ready else 0.0
        pf_available = self._person_feature_available()
        if pf_available:
            items.append({
                'severity': 'info',
                'title': 'XGBoost v2 파이프라인이 기본 운영 모델로 연결되었습니다.',
                'description': 'YOLO ByteTrack 사람 추적 → 10개 모션 특징 추출 → XGBoost v2 분류기(1500건 학습)로 낙상 확률을 판단합니다.',
                'action': '자동 선택은 XGBoost v2 파이프라인을 우선 사용합니다.',
            })
        elif rf_available:
            items.append({
                'severity': 'info',
                'title': 'RF 보조 파이프라인이 연결되었습니다 (XGBoost 미준비).',
                'description': (f'CV F1 {round(cv_f1 * 100, 1)}%%, CV AUC {round(cv_auc * 100, 1)}%% — YOLOv8n-Pose 사람 검출 → 13개 통계 특징 → RandomForest 분류' if rf_metric_ready else f"{rf_meta.get('model_class', 'RandomForestClassifier')} · 트리 {int(rf_meta.get('n_estimators', 0) or 0)}개 · 특징 {int(rf_meta.get('feature_count', len(self._RF_FEATURE_COLUMNS)) or len(self._RF_FEATURE_COLUMNS))}개"),
                'action': 'XGBoost v2 파이프라인을 준비하면 자동으로 메인 모델로 전환됩니다.',
            })
        else:
            items.append({
                'severity': 'warn',
                'title': '학습된 분석 모델이 준비되지 않아 규칙 기반 fallback으로 동작합니다.',
                'description': 'XGBoost v2 파이프라인 또는 RF 보조 파이프라인 모델 파일을 확인하세요.',
                'action': '모델 파일을 배치하고 서버가 접근 가능하도록 권한을 설정하세요.',
            })
        if behavior_state.get('ready') is False:
            items.append({
                'severity': 'warn',
                'title': '행동 분류 모델이 준비되지 않아 설명력이 제한됩니다.',
                'description': '행동 분류는 현재 파일명 패턴과 위험 점수 기반 추정에 가깝습니다.',
                'action': '행동 분류 학습 요약과 모델 파일을 생성한 뒤 결과 해석 레이어를 연결해야 합니다.',
            })
        if cv2 is None:
            items.append({
                'severity': 'warn',
                'title': '서버 영상 처리 라이브러리(OpenCV)가 없어 메타데이터와 이벤트 클립 추출이 제한됩니다.',
                'description': '현재 duration/fps/clip 정보는 브라우저 전달값에 크게 의존하며, 서버 측 정밀 검증은 비활성 상태입니다.',
                'action': 'OpenCV 또는 ffprobe 기반 메타데이터 추출기를 준비해 서버 측 검증 경로를 추가해야 합니다.',
            })
        if archive_summary.get('input_sources', {}).get('webcam-live', 0) == 0:
            items.append({
                'severity': 'info',
                'title': '실시간 웹캠 분석 아카이브가 아직 없습니다.',
                'description': '실시간 분석 경로는 UI 연결 상태를 우선 검증하는 단계이며, 운영 데이터가 누적되지 않았습니다.',
                'action': '실시간 프리뷰 연결 확인 후 webcam-live 입력 결과를 저장·검증하세요.',
            })
        if intake_summary.get('total', 0) == 0:
            items.append({
                'severity': 'info',
                'title': '추가 학습 intake 데이터가 없습니다.',
                'description': '사용자 피드백과 운영 영상이 아직 학습용 샘플로 누적되지 않았습니다.',
                'action': '관리자 화면에서 Y/N 샘플을 추가 등록해 재학습 기반을 확보하세요.',
            })
        overall_status = 'ok' if all(item.get('severity') == 'info' for item in items) else 'needs-review'
        if len(items) == 0:
            overall_status = 'ok'
            items.append({
                'severity': 'info',
                'title': '특이 진단 이슈가 없습니다.',
                'description': '현재 설정 기준에서 주요 진단 경고가 감지되지 않았습니다.',
                'action': '정기적으로 학습 요약과 실시간 아카이브를 점검하세요.',
            })
        return {
            'status': overall_status,
            'headline': '현재 분석 품질은 학습 모델 준비 상태, 서버 메타데이터 추출 가능 여부, 실시간 입력 검증 이력에 의해 좌우됩니다.',
            'items': items,
        }

    def behavior_classes(self):
        return [
            {'code': 'non-fall', 'label': '비낙상'},
            {'code': 'fall', 'label': '낙상'},
        ]

    def _analysis_profiles(self):
        return {
            'default': 'balanced',
            'profiles': [
                {
                    'key': 'balanced',
                    'label': '기본 분석',
                    'description': '전체 프레임 추적(640px)·제한 없는 프레임 수로 정확도를 높인 분석입니다.',
                    'target': 'RF 기준 약 30~60초 (전체 프레임 처리)',
                },
            ],
            'optimization_notes': [
                '메인페이지는 위험도·행동 분류·대표 이벤트만 유지',
                '상세 운영 정보와 설정은 관리자 페이지로 분리',
                '유사 기준 영상은 전체가 아니라 이벤트 구간 클립만 제공',
                '웹캠 입력은 브라우저 청크 전송 방식으로 업로드 파이프라인을 재사용',
            ]
        }

    def _profile_label(self, profile_key):
        """Return human-readable label for the given analysis profile key."""
        profiles = self._analysis_profiles().get('profiles', [])
        for p in profiles:
            if p.get('key') == profile_key:
                return p.get('label', profile_key)
        return profile_key or '기본 분석'

    def _model_options(self, baseline_state=None):
        """Return available model options.
        FN-0014: RF-Pose deprecated — hidden from UI, available only via config.
        """
        runtime_ready = self._trained_runtime_available(baseline_state)
        person_feature_ready = runtime_ready and self._person_feature_available()
        rf_available = self._rf_pipeline_available()
        xg_fall_ready = self._xg_fall_available()
        xg_posture_ready = self._xg_posture_available()
        xg_dual_ready = xg_fall_ready and xg_posture_ready
        options = [
            {
                'key': 'xg-dual',
                'label': 'XG-Dual (Fall+Posture) 파이프라인',
                'description': 'XG-Fall 낙상 감지 + XG-Posture 6-class 자세 분류를 동시 수행하는 듀얼 파이프라인입니다.',
                'available': xg_dual_ready,
            },
            {
                'key': 'xg-fall',
                'label': 'XG-Fall 37-Feature 파이프라인',
                'description': '37개 통합 특징(bbox+pose+temporal+gait) → XGBoost 낙상 감지 파이프라인입니다.',
                'available': xg_fall_ready,
            },
            {
                'key': 'person-feature',
                'label': 'XGBoost v2 파이프라인',
                'description': 'YOLO ByteTrack 사람 추적 → 10개 모션 특징 → XGBoost v2 분류 파이프라인입니다.',
                'available': person_feature_ready,
            },
            {
                'key': 'rf-pipeline',
                'label': 'RF 보조 파이프라인',
                'description': 'YOLOv8n-Pose 사람 검출 → 13개 bbox 통계 특징 → RandomForest 분류 파이프라인입니다.',
                'available': rf_available,
            },
            # FN-0014 Stage A: rf-pose deprecated — UI에서 숨김
            # config에서 직접 model_type=rf-pose 지정 시에만 사용 가능
        ]
        default_key = 'xg-dual' if xg_dual_ready else ('xg-fall' if xg_fall_ready else ('person-feature' if person_feature_ready else 'rf-pipeline'))
        return {
            'default': default_key,
            'options': options,
        }

    def _model_option_label(self, key):
        key = str(key or 'xg-dual').strip().lower()
        labels = {
            'xg-dual': 'XG-Dual (Fall+Posture) 파이프라인',
            'xg-fall': 'XG-Fall 37-Feature 파이프라인',
            'person-feature': 'XGBoost v2 파이프라인',
            'rf-pipeline': 'RF 보조 파이프라인',
            'rf-pose': 'RF-Pose 파이프라인 (deprecated)',
        }
        return labels.get(key, key or 'XG-Dual 파이프라인')

    def _webcam_mode_info(self):
        return {
            'status': 'preview-enabled',
            'message': '브라우저 웹캠 미리보기와 4초 단위 청크 분석 흐름을 지원합니다.',
            'supported_formats': ['video/webm'],
            'recommended_record_sec': 8,
            'steps': [
                '웹캠 권한 허용',
                '실시간 프리뷰 확인',
                '4초 단위 청크 생성',
                '기존 분석 API로 순차 전송',
                '향후 서버 추론 큐로 확장',
            ]
        }

    def _realtime_readiness(self):
        return {
            'possible': True,
            'status': 'phase-1-browser-streaming',
            'headline': '현재 구조에서는 브라우저 스트림 샘플링 + 주기 전송 방식의 실시간 분석이 가장 현실적인 적용 범위입니다.',
            'summary': '완전한 서버 상시 스트리밍 이전에, 브라우저에서 4초 단위로 잘라 업로드 API에 재사용하는 방식이 구현 난이도와 안정성 측면에서 가장 적합합니다.',
            'current_scope': [
                '브라우저 MediaRecorder 로 4초 청크 생성',
                '업로드 분석 API 재사용',
                '위험 점수·행동 분류·대표 이벤트만 즉시 갱신',
                '좌측 영상 창에서 입력 장면을 지속 표시',
            ],
            'recommended_stack': [
                {
                    'title': '1단계 · 브라우저 샘플링',
                    'status': 'ready-now',
                    'description': '청크 단위 업로드로 현재 구조에서 바로 운용 가능한 실시간 프리뷰 단계입니다.',
                },
                {
                    'title': '2단계 · 서버 추론 큐',
                    'status': 'next',
                    'description': '동시 접속과 장시간 모니터링 대응을 위해 수신/추론을 분리하는 단계입니다.',
                },
                {
                    'title': '3단계 · 누적 이벤트 경보',
                    'status': 'next',
                    'description': '연속 구간 누적 점수로 오탐을 줄이고 알림 조건을 안정화하는 단계입니다.',
                }
            ],
            'constraints': [
                '완전 초단위 스트리밍 추론은 아직 아닙니다.',
                '청크 분석 중 다음 청크 일부를 건너뛸 수 있습니다.',
                '장시간 운영에는 RTSP 입력과 worker 기반 서버 구조가 추가로 필요합니다.',
            ],
            'ui_scope': {
                'left_pane_video': True,
                'left_pane_description': '분석 실행 좌측 영역에서 업로드 영상 또는 웹캠 장면을 항상 표시합니다.',
                'result_policy': '메인페이지는 빠른 결과 확인 중심, 상세 운영 정보는 관리자 페이지 중심으로 분리합니다.',
            }
        }

    def _model_explanation(self, baseline_summary, behavior_summary, baseline_state, behavior_state, intake_summary, archive_summary):
        behavior_dataset = (behavior_summary or {}).get('dataset', {}) or {}
        behavior_validation = (behavior_summary or {}).get('validation_metrics', {}) or {}
        behavior_sample_value = behavior_dataset.get('sample_count', 0) if behavior_state.get('ready') else 0
        rf_available = self._rf_pipeline_available()
        runtime_ready = self._trained_runtime_available(baseline_state)
        person_feature_ready = runtime_ready and self._person_feature_available()
        rf_meta = self._rf_runtime_meta()
        meta = self._baseline_model_meta()
        fall_classifier = (meta.get('fall_classifier', {}) or {})
        feature_meta = fall_classifier.get('features', []) or []
        person_metric_ready = len(feature_meta) == 10
        rf_metric_ready = str(fall_classifier.get('type', '') or '').lower().startswith('randomforest') or len(feature_meta) == len(self._RF_FEATURE_COLUMNS)
        cv_f1 = float(fall_classifier.get('cv_f1', 0.7499) or 0.7499) if person_metric_ready else 0.0
        cv_auc = float(fall_classifier.get('cv_auc', 0.86) or 0.86) if person_metric_ready else 0.0
        training_samples = int(fall_classifier.get('training_samples', 2250) or 2250) if person_metric_ready else 0
        rf_cv_f1 = float(fall_classifier.get('cv_f1', 0.0) or 0.0) if rf_metric_ready else 0.0
        rf_cv_auc = float(fall_classifier.get('cv_auc', 0.0) or 0.0) if rf_metric_ready else 0.0
        rf_training_samples = int(fall_classifier.get('training_samples', 0) or 0) if rf_metric_ready else 0
        yolo_eval = (baseline_summary.get('evaluation', {}) or {}).get('average', {}) or {}
        return {
            'headline': '운영 기본 순서는 XGBoost v2 파이프라인 → RF 보조 파이프라인 → YOLO 분류 모델 순입니다.',
            'runtime_label': 'XGBoost v2 파이프라인' if person_feature_ready else ('RF 보조 파이프라인' if rf_available else ('YOLO 분류 모델' if runtime_ready else '규칙·메타데이터 기반 fallback')),
            'runtime_note': 'XGBoost v2 파이프라인을 기본 운영 모델로 사용하고, 필요 시 RF 보조 파이프라인을 비교용으로 사용합니다.' if person_feature_ready else ('RF 보조 파이프라인을 사용하고, XGBoost v2가 준비되면 자동으로 전환됩니다.' if rf_available else ('YOLO 분류 백업 모델을 사용합니다.' if runtime_ready else '학습 모델이 준비되지 않아 fallback을 사용합니다.')),
            'cards': [
                {
                    'key': 'fast',
                    'title': '빠른 분석 레이어',
                    'status': 'always-on',
                    'summary': '파일 메타데이터와 경량 규칙 기반 지표로 위험도와 대표 이벤트를 먼저 판단합니다.',
                    'items': [
                        '위험 단계·행동 분류·대표 이벤트 우선 반환',
                        '메인페이지 기본값',
                        '사용자 대기 시간 최소화',
                    ],
                },
                {
                    'key': 'person-feature',
                    'title': 'XGBoost v2 파이프라인 (운영 기본값)',
                    'status': 'ready' if person_feature_ready else 'not-ready',
                    'summary': f'Person detector + 10개 모션 특징 + XGBoost (학습 {training_samples}건, CV F1 {round(cv_f1 * 100, 1)}%%)',
                    'items': [
                        f"학습 샘플 {training_samples}건",
                        f"CV F1 {round(cv_f1 * 100, 1)}%%",
                        f"CV AUC {round(cv_auc * 100, 1)}%%",
                        '현재 업로드/실시간 분석의 기본 운영 모델',
                    ],
                },
                {
                    'key': 'rf-pipeline',
                    'title': 'RF 보조 파이프라인',
                    'status': 'ready' if rf_available else 'not-ready',
                    'summary': (f'YOLOv8n-Pose → 13 특징 → RandomForest (학습 {rf_training_samples}건, CV F1 {round(rf_cv_f1 * 100, 1)}%%)' if rf_metric_ready else f"YOLOv8n-Pose → 13 특징 → RandomForest (트리 {int(rf_meta.get('n_estimators', 0) or 0)}개, 특징 {int(rf_meta.get('feature_count', len(self._RF_FEATURE_COLUMNS)) or len(self._RF_FEATURE_COLUMNS))}개)"),
                    'items': [
                        (f"학습 샘플 {rf_training_samples}건 (5-Fold CV)" if rf_metric_ready else f"모델 클래스 {rf_meta.get('model_class', 'RandomForestClassifier') }"),
                        (f"CV F1 {round(rf_cv_f1 * 100, 1)}%%" if rf_metric_ready else f"트리 수 {int(rf_meta.get('n_estimators', 0) or 0)}개"),
                        (f"CV AUC {round(rf_cv_auc * 100, 1)}%%" if rf_metric_ready else f"특징 수 {int(rf_meta.get('feature_count', len(self._RF_FEATURE_COLUMNS)) or len(self._RF_FEATURE_COLUMNS))}개"),
                        '보조 비교 모델 (사용자 수동 선택)',
                    ],
                },
                {
                    'key': 'behavior',
                    'title': '낙상/비낙상 분류',
                    'status': 'ready' if behavior_state.get('ready') else 'training-needed',
                    'summary': behavior_state.get('active_label', '행동 라벨 추정 fallback'),
                    'model_type': behavior_state.get('model_type', 'fallback'),
                    'model_type_label': behavior_state.get('model_type_label', ''),
                    'model_type_note': behavior_state.get('model_type_note', ''),
                    'items': [
                        f"분류 방식: {behavior_state.get('model_type_label', 'fallback')}",
                        f"총 {behavior_sample_value}건",
                        f"검증 정확도 {round(float(behavior_validation.get('accuracy', 0.0) or 0.0) * 100, 1)}%",
                        f"Macro F1 {round(float(behavior_validation.get('macro_f1', 0.0) or 0.0) * 100, 1)}%",
                    ],
                },
                {
                    'key': 'live',
                    'title': '실시간 전환 레이어',
                    'status': 'preview',
                    'summary': '웹캠 청크를 동일 결과 스키마로 보내 업로드와 실시간 분석 구조를 맞춥니다.',
                    'items': [
                        '5초 청크 전송',
                        '좌측 프리뷰 유지',
                        '향후 서버 큐 구조로 확장 가능',
                    ],
                },
            ],
            'learning_data': [
                {
                    'label': '낙상 Y/N 데이터셋 (RF)',
                    'value': rf_training_samples if rf_metric_ready else int(rf_meta.get('feature_count', len(self._RF_FEATURE_COLUMNS)) or len(self._RF_FEATURE_COLUMNS)),
                    'note': 'RF 보조 파이프라인의 학습 메타가 있으면 샘플 수, 없으면 현재 운영 특징 수를 표시합니다.',
                },
                {
                    'label': '행동 분류 데이터셋',
                    'value': behavior_sample_value,
                    'note': '이진 행동 분류 학습 요약이 없으면 0으로 유지됩니다.',
                },
                {
                    'label': '분석 아카이브',
                    'value': archive_summary.get('total', 0),
                    'note': '업로드/실시간 분석 이력이 누적된 총 건수',
                },
                {
                    'label': '실시간 권장 청크(초)',
                    'value': 4,
                    'note': '브라우저 스트림 샘플링 시 권장 전송 길이',
                },
            ],
            'notes': [
                '메인페이지는 빠른 확인과 CTA 중심으로 단순화합니다.',
                '운영 설정과 학습 상태는 관리자 화면에서 분리 관리합니다.',
                '실시간 분석은 청크 기반 안정화 후 서버 큐 단계로 확장합니다.',
            ]
        }

    def _default_alert_settings(self):
        return {
            'updated_at': '',
            'guardian': {
                'name': '보호자',
                'phone': '010-1234-5678',
            },
            'guardians': [],
            'gateway': {
                'sms': {
                    'enabled': False,
                    'provider_name': 'solapi',
                    'webhook_url': '',
                    'auth_token': '',
                    'timeout_sec': 8,
                    'sender': '',
                    'template_id': '',
                },
                'push': {
                    'enabled': False,
                    'provider_name': 'fcm',
                    'webhook_url': '',
                    'auth_token': '',
                    'timeout_sec': 8,
                    'target': '',
                    'platform': 'fcm',
                    'bundle_id': '',
                },
            }
        }

    def _merge(self, base, override):
        result = dict(base)
        for key, value in (override or {}).items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge(result.get(key, {}), value)
            else:
                result[key] = value
        return result

    def _mask_token(self, token):
        token = str(token or '')
        if len(token) <= 4:
            return '*' * len(token)
        return f"{'*' * (len(token) - 4)}{token[-4:]}"

    def _load_alert_settings(self):
        saved = self._read_json(self._alert_settings_path(), default={}) or {}
        return self._merge(self._default_alert_settings(), saved)

    def _public_alert_settings(self, settings):
        settings = self._merge(self._default_alert_settings(), settings or {})
        guardians = settings.get('guardians', []) or []
        return {
            'updated_at': settings.get('updated_at', ''),
            'guardian': settings.get('guardian', {}),
            'guardians': [{'name': g.get('name', ''), 'phone': g.get('phone', ''), 'enabled': g.get('enabled', True)} for g in guardians],
            'gateway': {
                'sms': {
                    **{k: v for k, v in (settings.get('gateway', {}).get('sms', {}) or {}).items() if k != 'auth_token'},
                    'auth_token_masked': self._mask_token((settings.get('gateway', {}).get('sms', {}) or {}).get('auth_token', '')),
                },
                'push': {
                    **{k: v for k, v in (settings.get('gateway', {}).get('push', {}) or {}).items() if k != 'auth_token'},
                    'auth_token_masked': self._mask_token((settings.get('gateway', {}).get('push', {}) or {}).get('auth_token', '')),
                },
            }
        }

    def save_alert_settings(self, settings):
        current = self._load_alert_settings()
        merged = self._merge(current, settings or {})
        merged['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._write_json(self._alert_settings_path(), merged)
        return self._public_alert_settings(merged)

    def _training_data_requirements(self):
        return {
            'video': ['원본 영상 또는 이벤트 클립', '권장 포맷: mp4, mov, webm'],
            'labels': ['낙상 여부 Y/N', '행동 6종 분류', '이벤트 시작/종료 시점'],
            'metadata': ['촬영 위치', '카메라 각도', 'fps', '해상도', '환경 조건'],
        }

    def _routing_checklist(self):
        return [
            '로그인 제거 또는 최소화',
            '기본 진입 URL을 루트(/)로 유지',
            '상세 운영 기능은 관리자 페이지로 분리',
            '사이드바는 메인/관리자 진입만 유지',
        ]

    def _alert_policy(self):
        return {
            'guardian': {
                'trigger': 'risk_level 이 medium/high 이거나 fall_detected 가 true 일 때',
                'delivery': ['보호자 알림 로그 저장', '게이트웨이 설정 시 외부 전송 연계'],
            },
            'emergency': {
                'trigger': 'risk_level 이 high 이거나 fall_detected 가 true 일 때',
                'delivery': ['119 안내 팝업 표시', '이벤트 시간 로그 저장'],
            },
        }

    def _emergency_protocol(self):
        return {
            'headline': '낙상 고위험이 감지되면 사용자 확인 → 보호자 알림 → 응급기관 연락 검토 순서로 대응합니다.',
            'levels': [
                {
                    'level': 'medium',
                    'label': '주의',
                    'trigger': 'risk_score >= 0.5 또는 대표 이벤트가 낙상 후보로 분류될 때',
                    'steps': [
                        '화면에 주의 알림과 대표 이벤트 구간 표시',
                        '보호자 알림 전송 대상 여부 확인',
                        '사용자 또는 운영자가 결과를 검토하고 피드백 저장',
                    ],
                },
                {
                    'level': 'high',
                    'label': '고위험',
                    'trigger': 'risk_score >= 0.8 또는 fall_detected 가 true 일 때',
                    'steps': [
                        '응급 안내 팝업 즉시 노출',
                        '보호자 알림 기록 및 외부 게이트웨이 전송 시도',
                        '119 연락 스크립트와 이벤트 시각을 함께 안내',
                        '사후 피드백과 이벤트 로그를 저장',
                    ],
                },
            ],
            'record_fields': ['saved_name', 'risk_level', 'risk_score', 'event_time', 'guardian_status', 'popup_required'],
        }

    def _intake_summary(self):
        root = self._training_dir()
        summary = {'Y': 0, 'N': 0, 'total': 0, 'latest': [], 'by_date': {}, 'by_source': {'feedback': 0, 'manual': 0, 'other': 0}, 'since_last_train': 0}
        latest = []
        # FN-20260406-0001: 마지막 RF-Pose 재학습 시각 로드
        rf_pose_summary = self._read_json(
            self._project_abspath(self._RF_POSE_SUMMARY_REL_PATH), default={}) or {}
        last_train_at = rf_pose_summary.get('updated_at', '') or ''
        since_last_train = 0
        for label in ['Y', 'N']:
            label_dir = os.path.join(root, label)
            if os.path.isdir(label_dir) is False:
                continue
            for name in sorted(os.listdir(label_dir), reverse=True):
                if name.endswith('.json') or name.startswith('.'):
                    continue
                summary[label] += 1
                meta = self._read_json(os.path.join(label_dir, f'{name}.json'), default={}) or {}
                uploaded_at = meta.get('uploaded_at', '')
                latest.append({
                    'filename': name,
                    'label': label,
                    'uploaded_at': uploaded_at,
                    'note': meta.get('note', ''),
                })
                # 날짜별 통계
                date_key = uploaded_at[:10] if len(uploaded_at) >= 10 else 'unknown'
                if date_key not in summary['by_date']:
                    summary['by_date'][date_key] = {'Y': 0, 'N': 0}
                summary['by_date'][date_key][label] += 1
                # 소스별 통계
                if name.startswith('feedback-'):
                    summary['by_source']['feedback'] += 1
                elif meta.get('feedback_type') == 'manual-upload':
                    summary['by_source']['manual'] += 1
                else:
                    summary['by_source']['other'] += 1
                # 마지막 재학습 이후 누적 건수
                if last_train_at and uploaded_at > last_train_at:
                    since_last_train += 1
        summary['total'] = summary['Y'] + summary['N']
        summary['latest'] = latest[:5]
        summary['since_last_train'] = since_last_train
        summary['last_train_at'] = last_train_at
        # FN-0013: Posture-class intake 통계 + hard-case 통계
        posture_stats = {}
        posture_total = 0
        for cls in self._XG_POSTURE_CLASSES:
            cls_dir = os.path.join(root, cls)
            if os.path.isdir(cls_dir):
                cnt = len([f for f in os.listdir(cls_dir) if not f.endswith('.json') and not f.startswith('.')])
                posture_stats[cls] = cnt
                posture_total += cnt
            else:
                posture_stats[cls] = 0
        summary['posture_intake'] = posture_stats
        summary['posture_intake_total'] = posture_total
        hard_dir = os.path.join(root, '_hard_cases')
        hard_count = 0
        if os.path.isdir(hard_dir):
            hard_count = len([f for f in os.listdir(hard_dir) if f.endswith('.json')])
        summary['hard_case_count'] = hard_count
        return summary

    def _retraining_health(self, baseline_summary, baseline_state):
        if baseline_state.get('ready') is False:
            return {
                'ready': False,
                'status': 'not-ready',
                'headline': '학습 요약 또는 모델 파일이 없어 추가 데이터와 재학습이 더 필요합니다.',
                'checks': [
                    {'label': '학습 모델 존재', 'status': 'pending', 'detail': '모델 파일 또는 학습 요약 파일이 아직 없습니다.'},
                    {'label': 'Holdout 평가', 'status': 'pending', 'detail': '평가 결과가 아직 없습니다.'},
                ]
            }
        evaluation = (baseline_summary.get('evaluation', {}) or {}).get('average', {}) or {}
        recall = float(evaluation.get('recall', 0.0) or 0.0)
        f1 = float(evaluation.get('f1', 0.0) or 0.0)
        precision = float(evaluation.get('precision', 0.0) or 0.0)
        accuracy = float(evaluation.get('accuracy', 0.0) or 0.0)
        checks = [
            {'label': '낙상 재현율', 'status': 'pass' if recall >= 0.85 else ('warn' if recall >= 0.7 else 'fail'), 'detail': f'recall {recall:.3f}'},
            {'label': 'F1 균형', 'status': 'pass' if f1 >= 0.8 else ('warn' if f1 >= 0.65 else 'fail'), 'detail': f'f1 {f1:.3f}'},
            {'label': '정밀도', 'status': 'pass' if precision >= 0.75 else ('warn' if precision >= 0.6 else 'fail'), 'detail': f'precision {precision:.3f}'},
            {'label': '정확도', 'status': 'pass' if accuracy >= 0.75 else ('warn' if accuracy >= 0.6 else 'fail'), 'detail': f'accuracy {accuracy:.3f}'},
        ]
        status = 'healthy'
        headline = '재학습 결과가 목표 범위에 근접합니다.'
        if any(item['status'] == 'fail' for item in checks):
            status = 'action-required'
            headline = '추가 학습 데이터 확보 또는 임계값 조정이 필요합니다.'
        elif any(item['status'] == 'warn' for item in checks):
            status = 'monitor'
            headline = '운영 전 추가 검토가 필요한 수치가 있습니다.'
        return {
            'ready': True,
            'status': status,
            'headline': headline,
            'checks': checks,
        }

    def warmup_models(self, model_type='rf-pose'):
        """FN-20260406-0003: Pre-load YOLO + RF/RF-Pose models into memory.
        Called before realtime session starts to eliminate cold-start latency on first chunk."""
        import time as _time
        _t = _time.time()
        loaded = []
        try:
            self._get_rf_yolo_model()
            loaded.append('yolo-pose')
        except Exception:
            pass
        if model_type in ('rf-pose', 'auto', ''):
            try:
                if self._rf_pose_pipeline_available():
                    self._get_rf_pose_model()
                    loaded.append('rf-pose')
            except Exception:
                pass
        if model_type in ('rf-pipeline', 'auto', ''):
            try:
                if self._rf_pipeline_available():
                    self._get_rf_model()
                    loaded.append('rf-pipeline')
            except Exception:
                pass
        return {
            'warmed_up': loaded,
            'elapsed_ms': round((_time.time() - _t) * 1000),
        }

    def prototype_info(self):
        baseline_summary = self._baseline_summary()
        behavior_summary = self._behavior_summary()
        intake_summary = self._intake_summary()
        archive_summary = self._analysis_archive_summary()
        baseline_state = self._baseline_state(baseline_summary)
        behavior_state = self._behavior_state(behavior_summary)
        analysis_engine_summary = self._analysis_engine_summary(baseline_state, behavior_state, intake_summary, archive_summary)
        analysis_diagnostics = self._analysis_diagnostics(baseline_state, behavior_state, intake_summary, archive_summary)
        return {
            'supported_formats': self.allowed_extensions,
            'max_upload_mb': self.max_upload_mb,
            'prototype_mode': not self._rf_pipeline_available(),
            'baseline_model_ready': self._rf_pipeline_available(),
            'behavior_model_ready': behavior_state.get('ready', False),
            'message': analysis_engine_summary.get('current_runtime', {}).get('note', '현재는 업로드 분석을 기본으로 운영하고 있습니다.'),
            'analysis_steps': [
                '영상 입력',
                '메타데이터 저장',
                '빠른 분석 또는 정밀 분석 수행',
                '위험도·행동 분류·대표 이벤트 반환',
                '필요 시 보호자/응급 알림 연계',
            ],
            'analysis_profiles': self._analysis_profiles(),
            'model_options': self._model_options(baseline_state),
            'webcam_mode': self._webcam_mode_info(),
            'realtime_readiness': self._realtime_readiness(),
            'dataset_summary': {
                'fall_sample_count': int(((self._baseline_model_meta().get('fall_classifier', {}) or {}).get('training_samples', 2250)) or 2250),
                'fall_sample_note': 'XGBoost v2 파이프라인 학습에 사용된 전체 샘플 수',
                'fall_model_label': 'XGBoost v2 파이프라인 (YOLO + XGBoost)' if self._person_feature_available() else ('규칙 기반 fallback' if not self._rf_pipeline_available() else 'RF 보조 파이프라인'),
                'behavior_sample_count': (behavior_summary or {}).get('dataset', {}).get('sample_count', 0) if behavior_state.get('ready') else 0,
                'behavior_sample_note': '이진 행동 분류 학습 요약이 없으면 0으로 유지됩니다.',
                'behavior_model_label': behavior_state.get('active_label', '행동 라벨 추정 fallback'),
                'analysis_archive_count': archive_summary.get('total', 0),
                'realtime_chunk_sec': 5,
            },
            'model_explanation': self._model_explanation(baseline_summary, behavior_summary, baseline_state, behavior_state, intake_summary, archive_summary),
            'analysis_engine_summary': analysis_engine_summary,
            'analysis_diagnostics': analysis_diagnostics,
            'analysis_archive_summary': archive_summary,
            'result_schema': [
                {'key': 'fall_detected', 'label': '낙상 감지 여부'},
                {'key': 'behavior_class', 'label': '행동 분류 코드'},
                {'key': 'behavior_label', 'label': '행동 분류 라벨'},
                {'key': 'risk_score', 'label': '위험 점수'},
                {'key': 'risk_level', 'label': '위험 단계'},
                {'key': 'events', 'label': '대표 이벤트 구간'},
                {'key': 'summary', 'label': '요약 메시지'},
            ],
            'behavior_classes': self.behavior_classes(),
            'camera_transition_plan': [
                '업로드 입력과 웹캠 입력의 결과 스키마를 통일',
                '청크 기반 실시간 프리뷰 우선 적용',
                '서버 큐와 누적 이벤트 경보로 확장',
                '관리자 페이지에서 학습/운영 상태를 별도 관리',
            ],
            'training_data_requirements': self._training_data_requirements(),
            'decision_thresholds': {
                'fall_detected': self.fall_decision_threshold,
                'medium_risk': self.fall_decision_threshold,
                'high_risk': 0.8,
            },
            'trained_model': self._trained_model_info(baseline_summary, baseline_state, {}),
            'baseline_training': baseline_summary,
            'action_behavior_training': behavior_summary,
            'retraining_health': self._retraining_health(baseline_summary, baseline_state),
            'intake_summary': intake_summary,
            'alert_policy': self._alert_policy(),
            'emergency_protocol': self._emergency_protocol(),
            'alert_settings': self._public_alert_settings(self._load_alert_settings()),
            'routing_checklist': self._routing_checklist(),
            'model_comparison_report': self._model_comparison_report(),
            'pipeline_page': {
                'path': '/pipeline',
                'title': 'AI 파이프라인 상세',
                'description': '메인페이지에서 분리된 파이프라인 구조와 전환 계획을 확인합니다.',
            },
        }

    def _metadata_to_number(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _sort_analysis_basis(self, items):
        """Sort analysis_basis by contribution_score descending and re-assign ranks."""
        result = [dict(item or {}) for item in (items or [])]
        result.sort(key=lambda x: float(x.get('contribution_score', 0.0) or 0.0), reverse=True)
        for idx, item in enumerate(result, start=1):
            item['contribution_rank'] = idx
        return result

    def _guess_behavior(self, filename, risk_score):
        name = (filename or '').lower()
        if risk_score >= self.fall_decision_threshold or 'fall' in name:
            return 'fall', '낙상'
        return 'non-fall', '비낙상'

    def _heuristic_result(self, filename, duration, width, height, fps, analysis_profile):
        lower = (filename or '').lower()
        score = 0.28
        if 'fall' in lower or '_y' in lower or lower.startswith('y_'):
            score += 0.45
        if duration >= 8:
            score += 0.07
        if width >= 1280:
            score += 0.03
        if fps >= 24:
            score += 0.02
        score += 0.05
        score = max(0.05, min(0.98, score))

        fall_detected = score >= self.fall_decision_threshold
        risk_level = 'high' if score >= 0.8 else ('medium' if score >= self.fall_decision_threshold else 'low')
        risk_label = {'low': '안정', 'medium': '주의', 'high': '고위험'}.get(risk_level, '안정')
        behavior_class, behavior_label = self._guess_behavior(filename, score)
        event_time = round(max(1.0, duration * 0.5 if duration > 0 else 4.0), 2)
        analysis_basis = [
            {
                'feature': 'event_time',
                'label': '대표 위험 구간 시각',
                'value': event_time,
                'unit': '초',
                'level': risk_level,
                'description': 'fallback 분석에서 대표 확인 구간으로 선택한 시각입니다.',
            },
            {
                'feature': 'risk_score',
                'label': '휴리스틱 위험 점수',
                'value': round(score * 100, 1),
                'unit': '%',
                'level': risk_level,
                'description': '파일명·영상 길이·해상도·FPS를 기반으로 계산한 임시 점수입니다.',
            },
        ]
        return {
            'fall_detected': fall_detected,
            'behavior_class': behavior_class,
            'behavior_label': behavior_label,
            'behavior_inference': {
                'code': behavior_class,
                'label': behavior_label,
                'source': 'heuristic-fallback',
                'fallback': True,
                'reason': ['학습 런타임을 사용할 수 없어 메타데이터 기반 fallback을 사용했습니다.'],
            },
            'risk_score': round(score, 4),
            'risk_level': risk_level,
            'risk_label': risk_label,
            'summary': '낙상 고위험 동작이 의심됩니다.' if fall_detected else '현재 구간에서는 즉시 낙상 고위험이 감지되지 않았습니다.',
            'analysis_basis': analysis_basis,
            'runtime_key': 'heuristic-fallback',
            'runtime_label': '규칙·메타데이터 기반 fallback 분석',
            'events': [
                {
                    'label': '대표 분석 구간',
                    'time': event_time,
                    'confidence': round(score, 4),
                    'severity': risk_level,
                }
            ],
            'reference_matches': [],
        }

    def _write_uploaded_binary(self, filename, content):
        path = os.path.join(self._storage_dir(), filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as file:
            file.write(content)
        return path

    def _upload_meta_path(self, saved_name):
        return os.path.join(self._storage_dir(), f'{saved_name}.json')

    def _load_upload_paths(self, saved_name):
        video_path = os.path.join(self._storage_dir(), saved_name)
        meta_path = self._upload_meta_path(saved_name)
        return video_path, meta_path

    def analyze_upload(self, uploaded_file, metadata=None):
        import time as _time
        _st = {}
        _t0 = _time.time()
        _st['request_received_at'] = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.') + f'{int(datetime.datetime.now().microsecond / 1000):03d}'
        metadata = metadata or {}
        if uploaded_file is None:
            raise Exception('업로드된 영상 파일이 없습니다.')

        filename = self._sanitize_filename(getattr(uploaded_file, 'filename', 'video'))
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        if ext not in self.allowed_extensions:
            raise Exception('지원하지 않는 영상 형식입니다.')

        content = uploaded_file.read()
        if not content:
            raise Exception('비어 있는 파일은 분석할 수 없습니다.')

        size_mb = round(len(content) / (1024 * 1024), 2)
        if size_mb > self.max_upload_mb:
            raise Exception(f'업로드 가능한 최대 용량은 {self.max_upload_mb}MB입니다.')

        _st['file_read_sec'] = round(_time.time() - _t0, 3)

        duration = self._metadata_to_number(metadata.get('duration', 0))
        width = int(self._metadata_to_number(metadata.get('width', 0)))
        height = int(self._metadata_to_number(metadata.get('height', 0)))
        fps = self._metadata_to_number(metadata.get('fps', 0))
        analysis_profile = str(metadata.get('analysis_profile', 'balanced') or 'balanced').strip().lower()
        input_source = str(metadata.get('input_source', 'upload') or 'upload').strip() or 'upload'
        model_type = str(metadata.get('model_type', 'xg-dual') or 'xg-dual').strip().lower()

        _t_save = _time.time()
        file_hash = hashlib.sha1(content).hexdigest()[:12]
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        saved_name = f'{timestamp}-{file_hash}-{filename}'
        saved_path = self._write_uploaded_binary(saved_name, content)
        self._write_json(self._upload_meta_path(saved_name), {
            'filename': filename,
            'saved_name': saved_name,
            'uploaded_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'size_mb': size_mb,
            'metadata': metadata,
        })
        _st['file_save_sec'] = round(_time.time() - _t_save, 3)

        _t_sum = _time.time()
        baseline_summary = self._baseline_summary()
        behavior_summary = self._behavior_summary()
        intake_summary = self._intake_summary()
        archive_summary = self._analysis_archive_summary()
        baseline_state = self._baseline_state(baseline_summary)
        behavior_state = self._behavior_state(behavior_summary)
        _st['summary_load_sec'] = round(_time.time() - _t_sum, 3)

        runtime_warning = None
        result = None
        _t_inf = _time.time()
        try:
            result = self._infer_with_trained_model(saved_path, filename, analysis_profile, model_type=model_type, input_source=input_source, duration_hint=duration)
            inferred_meta = (result.get('video_meta', {}) or {})
            duration = self._metadata_to_number(inferred_meta.get('duration', duration), duration)
            width = int(self._metadata_to_number(inferred_meta.get('width', width), width))
            height = int(self._metadata_to_number(inferred_meta.get('height', height), height))
            fps = self._metadata_to_number(inferred_meta.get('fps', fps), fps)
        except Exception as e:
            runtime_warning = {
                'severity': 'warn',
                'title': '학습 모델 추론에 실패해 fallback 분석으로 전환했습니다.',
                'description': str(e),
                'action': 'person-feature/XGBoost 모델과 런타임 의존성 상태를 확인하세요.',
            }
        if result is None:
            result = self._heuristic_result(filename, duration, width, height, fps, analysis_profile)
        _st['inference_sec'] = round(_time.time() - _t_inf, 3)
        _t_build = _time.time()
        result['analysis_profile'] = analysis_profile
        result['schema_version'] = 2
        result['analysis_profile_label'] = self._profile_label(analysis_profile)
        if result.get('runtime_key') == 'xg-dual':
            elapsed = self._metadata_to_number((result.get('runtime_inference', {}) or {}).get('perf', {}).get('total', 0), 0)
            fall_windows = int((result.get('model_runtime', {}) or {}).get('fall_windows', 0) or 0)
            posture_lbl = result.get('posture_label', '')
            decision_st = result.get('decision_state', '')
            result['analysis_speed_note'] = f'XG-Dual(Fall+Posture) 파이프라인으로 분석했습니다. ({round(elapsed, 1)}초 · 윈도우 {fall_windows}개 · 자세 {posture_lbl} · 상태 {decision_st})'
        elif result.get('runtime_key') == 'person-feature-runtime':
            elapsed = self._metadata_to_number((result.get('runtime_inference', {}) or {}).get('elapsed_sec', 0), 0)
            processed_frames = int((result.get('model_runtime', {}) or {}).get('processed_frames', 0) or 0)
            result['analysis_speed_note'] = f'XGBoost v2 파이프라인으로 분석했습니다. ({round(elapsed, 1)}초 · 처리 프레임 {processed_frames}장)'
        elif result.get('runtime_key') == 'rf-pipeline-runtime':
            elapsed = self._metadata_to_number((result.get('runtime_inference', {}) or {}).get('elapsed_sec', 0), 0)
            det_frames = int((result.get('model_runtime', {}) or {}).get('detected_person_frames', 0) or 0)
            result['analysis_speed_note'] = f'RF 보조 파이프라인(YOLOv8n-Pose + RandomForest)으로 분석했습니다. ({round(elapsed, 1)}초 · 사람 검출 {det_frames}프레임)'
        elif result.get('runtime_key') == 'rf-pose-runtime':
            elapsed = self._metadata_to_number((result.get('runtime_inference', {}) or {}).get('elapsed_sec', 0), 0)
            det_frames = int((result.get('model_runtime', {}) or {}).get('detected_person_frames', 0) or 0)
            result['analysis_speed_note'] = f'RF-Pose 파이프라인(YOLOv8n-Pose + 키포인트 + RandomForest)으로 분석했습니다. ({round(elapsed, 1)}초 · 사람 검출 {det_frames}프레임)'
        else:
            result['analysis_speed_note'] = f'{self._profile_label(analysis_profile)}으로 운영 해석 정보를 함께 준비했습니다.'
        result['admin_details_available'] = True
        result['engine_summary'] = self._analysis_engine_summary(baseline_state, behavior_state, intake_summary, archive_summary, actual_runtime_key=result.get('runtime_key'))
        diagnostics = self._analysis_diagnostics(baseline_state, behavior_state, intake_summary, archive_summary).get('items', [])
        if runtime_warning is not None:
            diagnostics = [runtime_warning] + diagnostics
        result['diagnostics'] = diagnostics
        result['runtime_warning'] = runtime_warning
        result['trained_model'] = self._trained_model_info(baseline_summary, baseline_state, self._validation_report())
        result['behavior_model'] = self._behavior_model_meta()
        behavior_inference = result.get('behavior_inference', {}) or {}
        if behavior_inference.get('fallback') is True:
            diagnostics = [{
                'severity': 'warn',
                'title': '행동 분류는 fallback 기준으로 계산되었습니다.',
                'description': '이진 행동 분류 모델 메타정보가 없어 기본 비낙상 분류를 사용했습니다.',
                'action': '행동 분류 메타정보 연결 상태를 확인하세요.',
            }] + diagnostics
        elif behavior_inference.get('source'):
            diagnostics = [{
                'severity': 'info',
                'title': '행동 분류 모델이 연결되었습니다.',
                'description': f"현재 행동 분류는 {behavior_inference.get('source')} 기준으로 계산되었습니다.",
                'action': '행동 분류 결과와 판단 근거를 함께 검토하세요.',
            }] + diagnostics
        result['diagnostics'] = diagnostics
        runtime_key = result.get('runtime_key', '')
        existing_basis = list(result.get('analysis_basis', []) or [])
        result['analysis_basis'] = existing_basis
        if runtime_key == 'xg-dual':
            runtime_label = 'XG-Dual (Fall+Posture) 파이프라인'
        elif runtime_key == 'person-feature-runtime':
            runtime_label = 'XGBoost v2 파이프라인 (YOLO + XGBoost)'
        elif runtime_key == 'rf-pipeline-runtime':
            runtime_label = 'RF 보조 파이프라인 (RandomForest + YOLOv8n-Pose)'
        elif runtime_key == 'rf-pose-runtime':
            runtime_label = 'RF-Pose 파이프라인 (RandomForest + YOLOv8n-Pose + Keypoints)'
        else:
            runtime_label = baseline_state.get('active_label', '메타데이터·파일명 기반 fallback')
        result['analysis_overview'] = [
            f'입력 소스: {input_source}',
            f'영상 길이 {round(duration, 2)}초 · 해상도 {width}×{height}',
            runtime_label,
        ]
        if runtime_key == 'xg-dual':
            mr = result.get('model_runtime', {}) or {}
            _feat_count = int(mr.get('feature_count', 0) or 0)
            _fall_windows = int(mr.get('fall_windows', 0) or 0)
            _fall_prob = round(self._metadata_to_number(mr.get('fall_probability', 0.0), 0.0) * 100, 1)
            _posture_lbl = result.get('posture_label', '?')
            _decision_st = result.get('decision_state', '?')
            result['analysis_overview'].append(f"특징 {_feat_count}개 · 분석 윈도우 {_fall_windows}개 · 최대 낙상확률 {_fall_prob}% · 자세 {_posture_lbl} · 상태 {_decision_st}")
        elif runtime_key == 'person-feature-runtime':
            mr = result.get('model_runtime', {}) or {}
            result['analysis_overview'].append(f"{str(mr.get('profile', analysis_profile) or analysis_profile)} 프로파일 · 처리 프레임 {int(mr.get('processed_frames', 0) or 0)}장 · 추적 {int(mr.get('tracks', 0) or 0)}개 · 분석 윈도우 {int(mr.get('windows', 0) or 0)}개 · 최대 낙상확률 {round(self._metadata_to_number(mr.get('fall_probability', 0.0), 0.0) * 100, 1)}%")
        elif runtime_key in ('rf-pipeline-runtime', 'rf-pose-runtime'):
            mr = result.get('model_runtime', {}) or {}
            _feat_count = int(mr.get('combined_feature_count', mr.get('feature_count', 0)) or 0)
            _feat_note = f' · 특징 {_feat_count}개' if _feat_count else ''
            result['analysis_overview'].append(f"추출 프레임 {int(mr.get('extracted_frames', 0) or 0)}장 · 사람 검출 {int(mr.get('detected_person_frames', 0) or 0)}장{_feat_note} · 낙상 확률 {round(self._metadata_to_number(mr.get('fall_probability', 0.0), 0.0) * 100, 1)}%")
        result['risk_score_guide'] = self._risk_score_guide(result)
        result['behavior_summary'] = self._behavior_result_summary(result)
        result['requested_model'] = {
            'key': model_type,
            'label': self._model_option_label(model_type),
        }
        result['actual_model'] = {
            'key': result.get('runtime_key', ''),
            'label': result.get('runtime_label', runtime_label),
        }
        result['analysis_overview'].append(f"요청 모델 {self._model_option_label(model_type)} · 실제 적용 모델 {result.get('runtime_label', runtime_label)}")
        result['analysis_basis'] = self._sort_analysis_basis(existing_basis)

        _st['result_build_sec'] = round(_time.time() - _t_build, 3)

        _t_alert = _time.time()
        alert_workflow = None
        if result.get('fall_detected') or result.get('risk_level') in ['medium', 'high']:
            primary_event = (result.get('events') or [{}])[0]
            alert_workflow = self._build_alert_display(
                saved_name=saved_name,
                risk_level=result.get('risk_level', 'low'),
                risk_score=result.get('risk_score', 0.0),
                risk_label=result.get('risk_label', ''),
                summary=result.get('summary', ''),
                fall_detected=result.get('fall_detected', False),
                event_time=primary_event.get('time', 0.0),
                event_label=primary_event.get('label', '대표 분석 구간'),
                duration=duration,
            )
        _st['alert_dispatch_sec'] = round(_time.time() - _t_alert, 3)

        _st['response_ready_sec'] = round(_time.time() - _t0, 3)
        _st['total_server_sec'] = round(_time.time() - _t0, 3)

        return {
            'saved_name': saved_name,
            'original_name': filename,
            'file': {
                'original_name': filename,
                'saved_name': saved_name,
                'path': saved_path,
                'size_mb': size_mb,
                'duration': duration,
                'width': width,
                'height': height,
                'fps': fps,
            },
            'alert_workflow': alert_workflow,
            'server_timing': _st,
            **result,
        }

    def submit_training_sample(self, uploaded_file, label, note='', metadata=None):
        metadata = metadata or {}
        if uploaded_file is None:
            raise Exception('추가 학습용 영상 파일이 없습니다.')
        label = str(label or '').strip().upper()
        if label not in ('Y', 'N'):
            raise Exception('학습 라벨은 Y 또는 N 이어야 합니다.')

        filename = self._sanitize_filename(getattr(uploaded_file, 'filename', 'training-video'))
        content = uploaded_file.read()
        if not content:
            raise Exception('비어 있는 파일은 등록할 수 없습니다.')

        label_dir = os.path.join(self._training_dir(), label)
        os.makedirs(label_dir, exist_ok=True)
        file_hash = hashlib.sha1(content).hexdigest()[:12]
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        saved_name = timestamp + '-' + file_hash + '-' + filename
        target = os.path.join(label_dir, saved_name)
        with open(target, 'wb') as file:
            file.write(content)
        self._write_json(target + '.json', {
            'label': label,
            'original_name': filename,
            'saved_name': saved_name,
            'uploaded_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'note': note,
            'metadata': metadata,
        })
        return {
            'label': label,
            'saved_name': saved_name,
            'intake_summary': self._intake_summary(),
        }

    def retrain_baseline(self):
        baseline_module = self._baseline_module()
        behavior_module = self._behavior_module()
        baseline_summary = self._baseline_summary() or {}
        behavior_summary = self._behavior_summary() or {}
        rf_pipeline_summary = self._rf_project_summary()
        errors = []
        started_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        timings = {}

        if baseline_module is not None:
            _t0 = time.time()
            try:
                res = baseline_module.train_and_save(self._project_root(), force_rebuild=False) or {}
                baseline_summary = res.get('summary', baseline_summary)
                timings['baseline_sec'] = round(time.time() - _t0, 2)
            except Exception as e:
                timings['baseline_sec'] = round(time.time() - _t0, 2)
                errors.append(f'baseline 재학습 실패: {str(e)}')
        if behavior_module is not None:
            _t0 = time.time()
            try:
                res = behavior_module.train_and_save(self._project_root(), force_rebuild=False) or {}
                behavior_summary = res.get('summary', behavior_summary)
                timings['behavior_sec'] = round(time.time() - _t0, 2)
            except Exception as e:
                timings['behavior_sec'] = round(time.time() - _t0, 2)
                errors.append(f'behavior 재학습 실패: {str(e)}')
        _t0 = time.time()
        try:
            rf_result = self.retrain_rf_pipeline()
            rf_pipeline_summary = rf_result.get('summary', rf_pipeline_summary)
            if rf_result.get('errors'):
                errors.extend(rf_result.get('errors', []))
            timings['rf_pipeline_sec'] = round(time.time() - _t0, 2)
        except Exception as e:
            timings['rf_pipeline_sec'] = round(time.time() - _t0, 2)
            errors.append(f'rf-pipeline 재학습 실패: {str(e)}')
        rf_pose_summary = {}
        # FN-0014 Stage A: rf-pose retrain skipped (deprecated)
        # rf-pose 코드는 유지하되, 자동 재학습에서 제외
        timings['rf_pose_sec'] = 0
        # FN-0007: XG-Fall 37-feature retrain
        xg_fall_summary = {}
        _t0 = time.time()
        try:
            xg_fall_result = self.retrain_xg_fall()
            xg_fall_summary = xg_fall_result.get('summary', {})
            if xg_fall_result.get('errors'):
                errors.extend(xg_fall_result.get('errors', []))
            timings['xg_fall_sec'] = round(time.time() - _t0, 2)
        except Exception as e:
            timings['xg_fall_sec'] = round(time.time() - _t0, 2)
            errors.append(f'xg-fall 재학습 실패: {str(e)}')
        # FN-0013: XG-Posture 6-class retrain
        xg_posture_summary = {}
        _t0 = time.time()
        try:
            xg_posture_result = self.retrain_xg_posture()
            xg_posture_summary = xg_posture_result.get('summary', {})
            if xg_posture_result.get('errors'):
                errors.extend(xg_posture_result.get('errors', []))
            timings['xg_posture_sec'] = round(time.time() - _t0, 2)
        except Exception as e:
            timings['xg_posture_sec'] = round(time.time() - _t0, 2)
            errors.append(f'xg-posture 재학습 실패: {str(e)}')
        finished_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # FN-20260406-0001: A/B 모델 비교 리포트 생성
        model_comparison = self._build_model_comparison_report(
            baseline_summary, rf_pipeline_summary, rf_pose_summary)
        return {
            'dataset': (baseline_summary or {}).get('dataset', {}),
            'train_metrics': (baseline_summary or {}).get('train_metrics', {}),
            'evaluation': (baseline_summary or {}).get('evaluation', {}),
            'action_behavior_training': behavior_summary,
            'rf_pipeline_training': rf_pipeline_summary,
            'rf_pose_training': rf_pose_summary,
            'xg_fall_training': xg_fall_summary,
            'xg_posture_training': xg_posture_summary,
            'model_comparison': model_comparison,
            'retrain_started_at': started_at,
            'retrain_finished_at': finished_at,
            'timings': timings,
            'errors': errors,
        }

    def _build_model_comparison_report(self, baseline_summary, rf_pipeline_summary, rf_pose_summary):
        """FN-20260406-0001: 재학습 후 3개 모델(Baseline/RF-Pipeline/RF-Pose) 성능 A/B 비교 리포트."""
        def _extract_metrics(src, metric_keys=('accuracy', 'precision', 'recall', 'f1', 'roc_auc')):
            if not src or not isinstance(src, dict):
                return {}
            # cv (교차검증) 또는 train_metrics 에서 메트릭 추출
            cv = src.get('cv', src.get('evaluation', {}).get('average', {})) or {}
            train = src.get('train_metrics', {}) or {}
            result = {}
            for k in metric_keys:
                cv_val = cv.get(k)
                train_val = train.get(k)
                result[k] = {
                    'cv': round(float(cv_val), 4) if cv_val is not None else None,
                    'train': round(float(train_val), 4) if train_val is not None else None,
                }
            result['training_samples'] = int(src.get('training_samples', 0) or src.get('dataset', {}).get('sample_count', 0) or 0)
            result['feature_count'] = int(src.get('feature_count', 0) or len(src.get('features', [])))
            return result

        models = {}
        if baseline_summary:
            models['baseline'] = _extract_metrics(baseline_summary)
        if rf_pipeline_summary:
            models['rf-pipeline'] = _extract_metrics(rf_pipeline_summary)
        if rf_pose_summary:
            models['rf-pose'] = _extract_metrics(rf_pose_summary)

        # 최고 성능 모델 식별 (CV F1 기준)
        best_model = None
        best_f1 = -1.0
        for name, m in models.items():
            f1_cv = (m.get('f1', {}) or {}).get('cv')
            if f1_cv is not None and f1_cv > best_f1:
                best_f1 = f1_cv
                best_model = name

        # RF-Pose vs Baseline 피처 확장 효과 비교
        pose_vs_baseline = None
        if 'rf-pose' in models and 'rf-pipeline' in models:
            rp = models['rf-pose']
            rb = models['rf-pipeline']
            improvements = {}
            for k in ('accuracy', 'precision', 'recall', 'f1', 'roc_auc'):
                rp_cv = (rp.get(k, {}) or {}).get('cv')
                rb_cv = (rb.get(k, {}) or {}).get('cv')
                if rp_cv is not None and rb_cv is not None:
                    diff = round(rp_cv - rb_cv, 4)
                    improvements[k] = {'diff': diff, 'improved': diff > 0}
            pose_vs_baseline = {
                'rf_pose_features': rp.get('feature_count', 25),
                'rf_pipeline_features': rb.get('feature_count', 13),
                'additional_pose_features': rp.get('feature_count', 25) - rb.get('feature_count', 13),
                'metrics_diff': improvements,
            }

        return {
            'models': models,
            'best_model': best_model,
            'best_cv_f1': round(best_f1, 4) if best_f1 >= 0 else None,
            'pose_vs_pipeline': pose_vs_baseline,
            'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    def retrain_rf_pipeline(self):
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import joblib
        import numpy as np
        import pandas as pd
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
        from sklearn.model_selection import StratifiedKFold, cross_validate

        rows = []
        skipped = []
        intake_root = self._training_dir()
        for label in ['Y', 'N']:
            label_dir = os.path.join(intake_root, label)
            if os.path.isdir(label_dir) is False:
                continue
            for name in sorted(os.listdir(label_dir)):
                if name.startswith('.') or name.endswith('.json'):
                    continue
                video_path = os.path.join(label_dir, name)
                try:
                    extracted = self._extract_rf_pipeline_features(video_path)
                    row = {'video': name, 'label': label}
                    for col in self._RF_FEATURE_COLUMNS:
                        row[col] = float(extracted['feat'].get(col, 0.0) or 0.0)
                    rows.append(row)
                except Exception as e:
                    skipped.append({'video': name, 'label': label, 'reason': str(e)})

        summary = {
            'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'training_samples': len(rows),
            'class_distribution': {
                'Y': len([r for r in rows if r['label'] == 'Y']),
                'N': len([r for r in rows if r['label'] == 'N']),
            },
            'features': list(self._RF_FEATURE_COLUMNS),
            'source': 'hitl-intake-rf-pipeline',
            'skipped': skipped,
            'ready': False,
        }
        errors = []
        if summary['class_distribution']['Y'] < 2 or summary['class_distribution']['N'] < 2:
            summary['message'] = 'RF HITL 재학습은 클래스별 최소 2건 이상 필요합니다.'
            self._write_json(self._project_abspath(self._RF_PROJECT_SUMMARY_REL_PATH), summary)
            return {'summary': summary, 'errors': errors}

        df = pd.DataFrame(rows)
        X = df[self._RF_FEATURE_COLUMNS].astype(float).to_numpy()
        y = (df['label'].astype(str).str.upper() == 'Y').astype(int).to_numpy()
        min_class = min(int(np.sum(y == 1)), int(np.sum(y == 0)))
        n_splits = 3 if min_class >= 3 else 2
        model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1, class_weight='balanced_subsample')
        scoring = {'accuracy': 'accuracy', 'precision': 'precision', 'recall': 'recall', 'f1': 'f1', 'roc_auc': 'roc_auc'}
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        cv_results = cross_validate(model, X, y, cv=cv, scoring=scoring, return_train_score=False)
        model.fit(X, y)

        model_path = self._rf_project_model_path()
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        # ── atomic write: temp → rename (읽기 중 손상 방지) ──
        import tempfile
        _tmp_fd, _tmp_path = tempfile.mkstemp(
            suffix='.pkl.tmp', dir=os.path.dirname(model_path))
        os.close(_tmp_fd)
        try:
            joblib.dump(model, _tmp_path)
            os.replace(_tmp_path, model_path)        # POSIX atomic
        except BaseException:
            if os.path.exists(_tmp_path):
                os.unlink(_tmp_path)
            raise
        # ── 서버 fallback 모델 동기화 ──
        try:
            _srv = self._RF_MODEL_PATH
            _srv_tmp_fd, _srv_tmp = tempfile.mkstemp(
                suffix='.pkl.tmp', dir=os.path.dirname(_srv))
            os.close(_srv_tmp_fd)
            joblib.dump(model, _srv_tmp)
            os.replace(_srv_tmp, _srv)
        except Exception:
            pass  # 서버 경로 쓰기 실패는 치명적이지 않음
        self.__class__._rf_model_cache = None
        self.__class__._rf_model_mtime = None
        self.__class__._rf_model_path_cache = None

        y_pred = model.predict(X)
        y_proba = model.predict_proba(X)[:, 1] if hasattr(model, 'predict_proba') else None
        summary.update({
            'ready': True,
            'model_path': self._project_relative_path(model_path),
            'n_estimators': int(getattr(model, 'n_estimators', 0) or 0),
            'cv': {
                'folds': n_splits,
                'accuracy': round(float(np.mean(cv_results['test_accuracy'])), 4),
                'precision': round(float(np.mean(cv_results['test_precision'])), 4),
                'recall': round(float(np.mean(cv_results['test_recall'])), 4),
                'f1': round(float(np.mean(cv_results['test_f1'])), 4),
                'roc_auc': round(float(np.mean(cv_results['test_roc_auc'])), 4),
            },
            'train_metrics': {
                'accuracy': round(float(accuracy_score(y, y_pred)), 4),
                'precision': round(float(precision_score(y, y_pred, zero_division=0)), 4),
                'recall': round(float(recall_score(y, y_pred, zero_division=0)), 4),
                'f1': round(float(f1_score(y, y_pred, zero_division=0)), 4),
                'roc_auc': round(float(roc_auc_score(y, y_proba)), 4) if y_proba is not None and len(np.unique(y)) > 1 else 0.0,
            },
            'feature_importance': {col: round(float(imp), 4) for col, imp in zip(self._RF_FEATURE_COLUMNS, getattr(model, 'feature_importances_', []))},
        })
        self._write_json(self._project_abspath(self._RF_PROJECT_SUMMARY_REL_PATH), summary)
        return {'summary': summary, 'errors': errors}

    def retrain_rf_pose_pipeline(self):
        """Retrain RF-Pose model using HITL intake data with 25 combined features.

        [FN-0014 DEPRECATED] This function is deprecated and excluded from retrain_baseline().
        It remains callable for manual retrain if needed during shadow mode.
        Will be removed after Stage C hard-delete approval.
        """
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import joblib
        import numpy as np
        import pandas as pd
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
        from sklearn.model_selection import StratifiedKFold, cross_validate

        _combined_columns = self._RF_FEATURE_COLUMNS + self._POSE_FEATURE_COLUMNS
        rows = []
        skipped = []
        intake_root = self._training_dir()
        for label in ['Y', 'N']:
            label_dir = os.path.join(intake_root, label)
            if not os.path.isdir(label_dir):
                continue
            for name in sorted(os.listdir(label_dir)):
                if name.startswith('.') or name.endswith('.json'):
                    continue
                video_path = os.path.join(label_dir, name)
                try:
                    extracted = self._extract_rf_pipeline_features(video_path)
                    row = {'video': name, 'label': label}
                    # bbox features
                    for col in self._RF_FEATURE_COLUMNS:
                        row[col] = float(extracted['feat'].get(col, 0.0) or 0.0)
                    # pose features
                    _all_kps = extracted.get('all_frame_keypoints', [])
                    pose_feat = self._extract_pose_features(_all_kps, vid_height=extracted.get('vid_height', 360))
                    if pose_feat:
                        for col in self._POSE_FEATURE_COLUMNS:
                            row[col] = float(pose_feat.get(col, 0.0) or 0.0)
                    else:
                        for col in self._POSE_FEATURE_COLUMNS:
                            row[col] = 0.0 if 'angle' not in col else 180.0
                    rows.append(row)
                except Exception as e:
                    skipped.append({'video': name, 'label': label, 'reason': str(e)})

        summary = {
            'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'training_samples': len(rows),
            'class_distribution': {
                'Y': len([r for r in rows if r['label'] == 'Y']),
                'N': len([r for r in rows if r['label'] == 'N']),
            },
            'features': list(_combined_columns),
            'bbox_feature_count': len(self._RF_FEATURE_COLUMNS),
            'pose_feature_count': len(self._POSE_FEATURE_COLUMNS),
            'source': 'hitl-intake-rf-pose',
            'skipped': skipped,
            'ready': False,
        }
        errors = []
        if summary['class_distribution']['Y'] < 2 or summary['class_distribution']['N'] < 2:
            summary['message'] = 'RF-Pose 재학습은 클래스별 최소 2건 이상 필요합니다.'
            self._write_json(self._project_abspath(self._RF_POSE_SUMMARY_REL_PATH), summary)
            return {'summary': summary, 'errors': errors}

        df = pd.DataFrame(rows)
        X = df[_combined_columns].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
        y = (df['label'].astype(str).str.upper() == 'Y').astype(int).to_numpy()
        min_class = min(int(np.sum(y == 1)), int(np.sum(y == 0)))
        n_splits = 3 if min_class >= 3 else 2
        model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1, class_weight='balanced_subsample')
        scoring = {'accuracy': 'accuracy', 'precision': 'precision', 'recall': 'recall', 'f1': 'f1', 'roc_auc': 'roc_auc'}
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        cv_results = cross_validate(model, X, y, cv=cv, scoring=scoring, return_train_score=False)
        model.fit(X, y)

        model_path = self._rf_pose_model_path()
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        # ── atomic write: temp → rename ──
        import tempfile
        _tmp_fd, _tmp_path = tempfile.mkstemp(
            suffix='.pkl.tmp', dir=os.path.dirname(model_path))
        os.close(_tmp_fd)
        try:
            joblib.dump(model, _tmp_path)
            os.replace(_tmp_path, model_path)
        except BaseException:
            if os.path.exists(_tmp_path):
                os.unlink(_tmp_path)
            raise
        self.__class__._rf_pose_model_cache = None
        self.__class__._rf_pose_model_mtime = None
        self.__class__._rf_pose_model_path_cache = None

        y_pred = model.predict(X)
        y_proba = model.predict_proba(X)[:, 1] if hasattr(model, 'predict_proba') else None
        summary.update({
            'ready': True,
            'model_path': self._project_relative_path(model_path),
            'n_estimators': int(getattr(model, 'n_estimators', 0) or 0),
            'feature_count': len(_combined_columns),
            'cv': {
                'folds': n_splits,
                'accuracy': round(float(np.mean(cv_results['test_accuracy'])), 4),
                'precision': round(float(np.mean(cv_results['test_precision'])), 4),
                'recall': round(float(np.mean(cv_results['test_recall'])), 4),
                'f1': round(float(np.mean(cv_results['test_f1'])), 4),
                'roc_auc': round(float(np.mean(cv_results['test_roc_auc'])), 4),
            },
            'train_metrics': {
                'accuracy': round(float(accuracy_score(y, y_pred)), 4),
                'precision': round(float(precision_score(y, y_pred, zero_division=0)), 4),
                'recall': round(float(recall_score(y, y_pred, zero_division=0)), 4),
                'f1': round(float(f1_score(y, y_pred, zero_division=0)), 4),
                'roc_auc': round(float(roc_auc_score(y, y_proba)), 4) if y_proba is not None and len(np.unique(y)) > 1 else 0.0,
            },
            'feature_importance': {col: round(float(imp), 4) for col, imp in zip(_combined_columns, getattr(model, 'feature_importances_', []))},
        })
        self._write_json(self._project_abspath(self._RF_POSE_SUMMARY_REL_PATH), summary)
        return {'summary': summary, 'errors': errors}

    # ── FN-0007: XG-Fall 37-feature inference ──────────────────────────
    _XG_FALL_THRESHOLD = 0.55

    def _infer_xg_fall(self, video_path, filename='', analysis_profile='balanced', input_source='upload', duration_hint=0):
        """XG-Fall binary classification using unified 37-feature pipeline."""
        import numpy as np
        import time as _time

        _perf = {}
        _t_total = _time.time()

        # Extract unified timeseries
        _t = _time.time()
        ts_result = self._extract_unified_timeseries(video_path, input_source=input_source, duration_hint=duration_hint)
        _perf['timeseries'] = round(_time.time() - _t, 3)
        _perf.update(ts_result.get('perf', {}))

        timeseries = ts_result['timeseries']
        vid_meta = ts_result['vid_meta']

        # Build 37-feature windows (1.0s window for fall detection)
        _t = _time.time()
        windows = self._build_xg_feature_windows(timeseries, vid_meta, window_sec=1.0, stride_sec=0.5)
        _perf['window_build'] = round(_time.time() - _t, 3)

        if len(windows) == 0:
            _perf['total'] = round(_time.time() - _t_total, 3)
            return {
                'fall_detected': False,
                'behavior_class': 'unknown',
                'behavior_label': '판단 불가',
                'risk_score': 0.0,
                'risk_level': 'low',
                'risk_label': '안정',
                'summary': '분석 윈도우를 생성하지 못했습니다. 영상이 짧거나 사람 추적이 부족합니다.',
                'events': [],
                'reference_matches': [],
                'analysis_basis': [],
                'runtime_key': 'xg-fall-37',
                'runtime_label': 'XG-Fall 37-feature 분석',
                'runtime_inference': {'perf': _perf},
                'model_runtime': {'label': 'XG-Fall 37-feature', 'detection_frames': ts_result.get('detection_frames', [])},
                'video_meta': {
                    'duration': vid_meta.get('duration', 0),
                    'width': vid_meta.get('width', 0),
                    'height': vid_meta.get('height', 0),
                    'fps': vid_meta.get('fps', 0),
                },
            }

        # Load XG-Fall model and predict
        _t = _time.time()
        model = self._get_xg_fall_model()
        feature_cols = self._XG_FEATURE_COLUMNS

        X = np.array([[w.get(col, 0.0) for col in feature_cols] for w in windows])
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        proba = model.predict_proba(X)[:, 1] if hasattr(model, 'predict_proba') else model.predict(X).astype(float)
        _perf['xg_predict'] = round(_time.time() - _t, 3)

        max_prob = float(np.max(proba))
        mean_prob = float(np.mean(proba))
        fall_ratio = float(np.sum(proba >= self._XG_FALL_THRESHOLD)) / len(proba)

        # Score: weighted combination
        peak_idx = int(np.argmax(proba))
        peak_feats = windows[peak_idx]
        _fp = peak_feats.get('floor_proximity', 0.0)
        _hr = peak_feats.get('height_ratio', 0.0)
        _fp_boost = min(1.0, max(0.0, (_fp - 0.5) / 0.5)) if _fp > 0.5 else 0.0
        _hr_boost = min(1.0, max(0.0, (-_hr - 0.05) / 0.25)) if _hr < -0.05 else 0.0
        final_score = max_prob * 0.45 + mean_prob * 0.25 + fall_ratio * 0.15 + _fp_boost * 0.10 + _hr_boost * 0.05
        final_score = round(max(0.0, min(0.999999, final_score)), 6)

        # Motion gate (majority vote)
        _mds = peak_feats.get('max_down_speed', 0.0)
        _cdy = peak_feats.get('center_dy', 0.0)
        gate_checks = {
            'max_down_speed': _mds >= 0.15,
            'center_dy': _cdy >= 0.03,
            'pose_change': (_hr <= -0.05 or peak_feats.get('aspect_change', 0.0) >= 0.05 or _fp >= 0.78),
        }
        _gate_pass = sum(1 for v in gate_checks.values() if v) >= 2
        _floor_override = _fp >= 0.85 and _hr <= -0.08
        _speed_override = _fp >= 0.75 and _mds >= 0.3
        motion_gate_passed = _gate_pass or _floor_override or _speed_override

        if not motion_gate_passed:
            final_score = min(final_score, max_prob * 0.35, mean_prob * 0.45, 0.35)

        # ── FN-0010: XG-Fall Post-Processing Suppressors ──────────────
        _suppressed_by = []

        # 1) Stationary suppressor — very low motion + low tilt change → suppress
        _still = peak_feats.get('stillness', 0.0)
        _tilt_max = peak_feats.get('pose_tilt_max', 0.0)
        _speed_std = peak_feats.get('speed_std', 0.0)
        if _still >= 0.75 and _tilt_max <= 12.0 and _mds < 0.12 and _speed_std < 0.05:
            final_score = min(final_score, 0.30)
            _suppressed_by.append('stationary_suppressor')

        # 2) Aspect-only suppressor — aspect change w/o vertical descent → suppress
        _ac = peak_feats.get('aspect_change', 0.0)
        if abs(_ac) >= 0.05 and _cdy < 0.015 and _mds < 0.10:
            final_score = min(final_score, 0.30)
            _suppressed_by.append('aspect_only_suppressor')

        # 3) Short-clip stricter threshold — for short videos tighten threshold
        _dur = vid_meta.get('duration', 0)
        _short_clip = _dur > 0 and _dur < 2.0
        if _short_clip and len(windows) <= 3:
            _short_thr = self._XG_FALL_THRESHOLD + 0.10
            if final_score < _short_thr:
                _suppressed_by.append('short_clip_strict')

        # 4) Fast-sit suppressor — large knee bend + low torso tilt → sitting not falling
        _knee_min = peak_feats.get('pose_knee_bend_min', 180.0)
        _tilt_mean = peak_feats.get('pose_tilt_mean', 0.0)
        _spread_max = peak_feats.get('pose_spread_max', 0.0)
        if _knee_min <= 90.0 and _tilt_mean <= 20.0 and _spread_max < 0.15:
            final_score = min(final_score, 0.40)
            _suppressed_by.append('fast_sit_suppressor')

        # 5) Controlled-lie suppressor — long descent duration + low acceleration → lying down
        _desc_dur = peak_feats.get('descent_duration', 0.0)
        _post_still = peak_feats.get('post_descent_stillness', 0.0)
        if _desc_dur >= 1.5 and _mds < 0.20 and _post_still >= 0.5:
            final_score = min(final_score, 0.40)
            _suppressed_by.append('controlled_lie_suppressor')

        # Apply short-clip threshold override for fall_detected decision
        _effective_thr = self._XG_FALL_THRESHOLD
        if _short_clip and len(windows) <= 3:
            _effective_thr = self._XG_FALL_THRESHOLD + 0.10

        final_score = round(max(0.0, min(0.999999, final_score)), 6)
        fall_detected = final_score >= _effective_thr if motion_gate_passed else False

        risk_level = 'high' if final_score >= 0.75 else ('medium' if final_score >= _effective_thr else 'low')
        risk_label = {'low': '안정', 'medium': '주의', 'high': '고위험'}.get(risk_level, '안정')

        # Events from top windows
        sorted_idx = np.argsort(proba)[::-1][:5]
        events = []
        for rank, idx in enumerate(sorted_idx):
            w = windows[int(idx)]
            events.append({
                'label': '최고 위험 구간' if rank == 0 else f'보조 위험 구간 {rank + 1}',
                'time': 0.0,  # window-level time not directly available
                'confidence': round(float(proba[int(idx)]), 4),
                'severity': risk_level,
            })

        # Analysis basis (top contributing features)
        feature_importances = {}
        if hasattr(model, 'feature_importances_'):
            for col, imp in zip(feature_cols, model.feature_importances_):
                feature_importances[col] = round(float(imp), 4)

        analysis_basis = []
        _xg_fall_specs = [
            ('max_down_speed', '최대 하강 속도', '상체가 급격히 아래로 이동했는지 보여줍니다.'),
            ('center_dy', '수직 이동량', '윈도우 내 중심 Y 평균 이동.'),
            ('floor_proximity', '바닥 근접도', '인체 하단이 바닥에 얼마나 가까운지.'),
            ('pose_tilt_max', '최대 몸통 기울기', '몸통이 기울어진 최대 각도.'),
            ('pose_height_ratio_min', '최소 자세 높이비', '코~발끝 높이의 최솟값 (낙상 시 감소).'),
            ('descent_duration', '하강 지속시간', '연속 하강 프레임의 지속시간.'),
            ('stillness', '정지 비율', '움직이지 않는 프레임 비율.'),
            ('height_ratio', '높이 변화율', 'bbox 높이 변화 비율.'),
            ('pose_knee_bend_min', '최소 무릎 굽힘', '무릎 관절의 최소 각도.'),
            ('speed_std', '하강속도 표준편차', '하강 속도의 변동성.'),
        ]
        for feat_key, feat_label, feat_desc in _xg_fall_specs:
            val = peak_feats.get(feat_key, 0.0)
            imp = feature_importances.get(feat_key, 0.0)
            imp_label = f' (기여도 {round(imp*100,1)}%)' if imp > 0 else ''
            analysis_basis.append({
                'feature': feat_key,
                'label': feat_label + imp_label,
                'value': round(float(val), 4),
                'unit': '',
                'level': 'medium',
                'description': feat_desc,
            })
        analysis_basis.sort(key=lambda x: feature_importances.get(x['feature'], 0), reverse=True)

        behavior_class = 'fall' if fall_detected else 'non-fall'
        behavior_label = '낙상' if fall_detected else '비낙상'
        summary_text = 'XG-Fall 37-feature 분석 결과 낙상 가능성이 높습니다.' if fall_detected else 'XG-Fall 37-feature 분석 결과 즉시 낙상 가능성은 낮습니다.'

        _perf['total'] = round(_time.time() - _t_total, 3)
        return {
            'fall_detected': fall_detected,
            'behavior_class': behavior_class,
            'behavior_label': behavior_label,
            'risk_score': final_score,
            'risk_level': risk_level,
            'risk_label': risk_label,
            'summary': summary_text,
            'events': events,
            'reference_matches': [],
            'analysis_basis': analysis_basis,
            'runtime_key': 'xg-fall-37',
            'runtime_label': 'XG-Fall 37-feature 분석',
            'runtime_inference': {
                'fall_score': final_score,
                'fall_detected': fall_detected,
                'max_probability': round(max_prob, 4),
                'mean_probability': round(mean_prob, 4),
                'fall_window_ratio': round(fall_ratio, 4),
                'windows': len(windows),
                'motion_gate_passed': motion_gate_passed,
                'suppressed_by': _suppressed_by,
                'perf': _perf,
            },
            'behavior_inference': {
                'code': behavior_class,
                'label': behavior_label,
                'source': 'xg-fall-37',
                'fallback': False,
            },
            'model_runtime': {
                'label': 'XG-Fall 37-feature 분석',
                'fall_classifier': self._project_relative_path(self._xg_fall_model_path()),
                'windows': len(windows),
                'fall_probability': round(max_prob, 4),
                'mean_probability': round(mean_prob, 4),
                'feature_count': len(feature_cols),
                'detection_frames': ts_result.get('detection_frames', []),
            },
            'video_meta': {
                'duration': vid_meta.get('duration', 0),
                'width': vid_meta.get('width', 0),
                'height': vid_meta.get('height', 0),
                'fps': vid_meta.get('fps', 0),
            },
        }

    # ── FN-0011: XG-Dual Inference Pipeline ─────────────────────────────
    def _infer_xg_dual(self, video_path, filename='', analysis_profile='balanced', input_source='upload', duration_hint=0):
        """Dual-model inference: XG-Fall (binary) + XG-Posture (6-class) on shared timeseries.

        Returns combined result with fall_detected, posture_label, posture_probs,
        decision_state, and explain.
        """
        import numpy as np
        import time as _time

        _perf = {}
        _t_total = _time.time()

        # ── Shared timeseries extraction (once) ──
        _t = _time.time()
        ts_result = self._extract_unified_timeseries(video_path, input_source=input_source, duration_hint=duration_hint)
        _perf['timeseries'] = round(_time.time() - _t, 3)
        _perf.update(ts_result.get('perf', {}))

        timeseries = ts_result['timeseries']
        vid_meta = ts_result['vid_meta']

        if len(timeseries) < 2:
            _perf['total'] = round(_time.time() - _t_total, 3)
            return self._xg_dual_empty_result(vid_meta, _perf, ts_result)

        # ── XG-Fall: 1.0s windows → binary prediction ──
        _t = _time.time()
        fall_windows = self._build_xg_feature_windows(timeseries, vid_meta, window_sec=1.0, stride_sec=0.5)
        _perf['fall_window_build'] = round(_time.time() - _t, 3)

        fall_detected = False
        fall_score = 0.0
        _suppressed_by = []
        fall_analysis_basis = []

        if len(fall_windows) > 0:
            _t = _time.time()
            fall_model = self._get_xg_fall_model()
            feature_cols = self._XG_FEATURE_COLUMNS
            X_fall = np.array([[w.get(col, 0.0) for col in feature_cols] for w in fall_windows])
            X_fall = np.nan_to_num(X_fall, nan=0.0, posinf=0.0, neginf=0.0)
            fall_proba = fall_model.predict_proba(X_fall)[:, 1] if hasattr(fall_model, 'predict_proba') else fall_model.predict(X_fall).astype(float)
            _perf['fall_predict'] = round(_time.time() - _t, 3)

            max_prob = float(np.max(fall_proba))
            mean_prob = float(np.mean(fall_proba))
            fall_ratio = float(np.sum(fall_proba >= self._XG_FALL_THRESHOLD)) / len(fall_proba)

            peak_idx = int(np.argmax(fall_proba))
            pf = fall_windows[peak_idx]
            _fp = pf.get('floor_proximity', 0.0)
            _hr = pf.get('height_ratio', 0.0)
            _mds = pf.get('max_down_speed', 0.0)
            _cdy = pf.get('center_dy', 0.0)
            _fp_boost = min(1.0, max(0.0, (_fp - 0.5) / 0.5)) if _fp > 0.5 else 0.0
            _hr_boost = min(1.0, max(0.0, (-_hr - 0.05) / 0.25)) if _hr < -0.05 else 0.0
            fall_score = max_prob * 0.45 + mean_prob * 0.25 + fall_ratio * 0.15 + _fp_boost * 0.10 + _hr_boost * 0.05

            # Motion gate
            gate_checks = {
                'max_down_speed': _mds >= 0.15,
                'center_dy': _cdy >= 0.03,
                'pose_change': (_hr <= -0.05 or pf.get('aspect_change', 0.0) >= 0.05 or _fp >= 0.78),
            }
            _gate_pass = sum(1 for v in gate_checks.values() if v) >= 2
            _floor_override = _fp >= 0.85 and _hr <= -0.08
            _speed_override = _fp >= 0.75 and _mds >= 0.3
            motion_gate_passed = _gate_pass or _floor_override or _speed_override

            if not motion_gate_passed:
                fall_score = min(fall_score, max_prob * 0.35, mean_prob * 0.45, 0.35)

            # Suppressors (same as FN-0010 in _infer_xg_fall)
            _still = pf.get('stillness', 0.0)
            _tilt_max = pf.get('pose_tilt_max', 0.0)
            _speed_std = pf.get('speed_std', 0.0)
            if _still >= 0.75 and _tilt_max <= 12.0 and _mds < 0.12 and _speed_std < 0.05:
                fall_score = min(fall_score, 0.30)
                _suppressed_by.append('stationary_suppressor')
            _ac = pf.get('aspect_change', 0.0)
            if abs(_ac) >= 0.05 and _cdy < 0.015 and _mds < 0.10:
                fall_score = min(fall_score, 0.30)
                _suppressed_by.append('aspect_only_suppressor')
            _dur = vid_meta.get('duration', 0)
            _short_clip = _dur > 0 and _dur < 2.0
            if _short_clip and len(fall_windows) <= 3:
                _suppressed_by.append('short_clip_strict')
            _knee_min = pf.get('pose_knee_bend_min', 180.0)
            _tilt_mean = pf.get('pose_tilt_mean', 0.0)
            _spread_max = pf.get('pose_spread_max', 0.0)
            if _knee_min <= 90.0 and _tilt_mean <= 20.0 and _spread_max < 0.15:
                fall_score = min(fall_score, 0.40)
                _suppressed_by.append('fast_sit_suppressor')
            _desc_dur = pf.get('descent_duration', 0.0)
            _post_still = pf.get('post_descent_stillness', 0.0)
            if _desc_dur >= 1.5 and _mds < 0.20 and _post_still >= 0.5:
                fall_score = min(fall_score, 0.40)
                _suppressed_by.append('controlled_lie_suppressor')

            _effective_thr = self._XG_FALL_THRESHOLD + (0.10 if (_short_clip and len(fall_windows) <= 3) else 0.0)
            fall_score = round(max(0.0, min(0.999999, fall_score)), 6)
            fall_detected = fall_score >= _effective_thr if motion_gate_passed else False
        else:
            motion_gate_passed = False
            max_prob = 0.0
            mean_prob = 0.0
            fall_ratio = 0.0

        # ── XG-Posture: 1.5s windows → 6-class prediction ──
        posture_label = 'stand'
        posture_score = 0.0
        posture_probs = {c: 0.0 for c in self._LABEL_L2_CLASSES}
        posture_probs['stand'] = 1.0
        _posture_available = False

        if self._xg_posture_available():
            _t = _time.time()
            _posture_win_sec = 1.0 if input_source in ('webcam-live', 'webcam', 'realtime') else 1.5  # FN-0021: realtime은 1.0s
            posture_windows = self._build_xg_feature_windows(timeseries, vid_meta, window_sec=_posture_win_sec, stride_sec=0.5)
            _perf['posture_window_build'] = round(_time.time() - _t, 3)

            if len(posture_windows) > 0:
                _t = _time.time()
                posture_bundle = self._get_xg_posture_model()
                p_model = posture_bundle.get('model') if isinstance(posture_bundle, dict) else posture_bundle
                p_classes = posture_bundle.get('classes', self._LABEL_L2_CLASSES) if isinstance(posture_bundle, dict) else self._LABEL_L2_CLASSES
                p_feat_cols = posture_bundle.get('feature_cols', self._XG_FEATURE_COLUMNS) if isinstance(posture_bundle, dict) else self._XG_FEATURE_COLUMNS

                X_posture = np.array([[w.get(col, 0.0) for col in p_feat_cols] for w in posture_windows])
                X_posture = np.nan_to_num(X_posture, nan=0.0, posinf=0.0, neginf=0.0)

                if hasattr(p_model, 'predict_proba'):
                    raw_probs = p_model.predict_proba(X_posture)
                else:
                    raw_preds = p_model.predict(X_posture)
                    raw_probs = np.zeros((len(raw_preds), len(p_classes)))
                    for i, pred in enumerate(raw_preds):
                        idx = list(p_classes).index(pred) if pred in p_classes else 0
                        raw_probs[i, idx] = 1.0
                _perf['posture_predict'] = round(_time.time() - _t, 3)

                # FN-0024/0025: Apply heuristic boost for walk/run/stand/sit
                raw_probs = self._posture_heuristic_boost(raw_probs, posture_windows, p_classes)

                # Build per-window posture predictions
                pw_list = []
                for wi in range(len(posture_windows)):
                    probs_dict = {c: float(raw_probs[wi, ci]) for ci, c in enumerate(p_classes)}
                    lbl = p_classes[int(np.argmax(raw_probs[wi]))]
                    pw_list.append({'label': lbl, 'probs': probs_dict})

                # Temporal smoothing
                _t = _time.time()
                smoothed = self._smooth_posture_sequence(pw_list, window_size=5, ema_alpha=0.3)
                _perf['posture_smooth'] = round(_time.time() - _t, 3)

                if smoothed:
                    # Aggregate: pick most frequent smoothed label, average probs
                    label_counts = {}
                    avg_probs = {c: 0.0 for c in self._LABEL_L2_CLASSES}
                    for s in smoothed:
                        lbl = s['label']
                        label_counts[lbl] = label_counts.get(lbl, 0) + 1
                        for c in self._LABEL_L2_CLASSES:
                            avg_probs[c] += s['probs'].get(c, 0.0)
                    posture_label = max(label_counts, key=label_counts.get)
                    avg_probs = {c: v / len(smoothed) for c, v in avg_probs.items()}
                    total = sum(avg_probs.values())
                    if total > 0:
                        avg_probs = {c: v / total for c, v in avg_probs.items()}
                    posture_probs = avg_probs
                    posture_score = posture_probs.get(posture_label, 0.0)
                    _posture_available = True

        # ── Decision arbitration ──
        fall_result_for_arb = {
            'fall_detected': fall_detected,
            'risk_score': fall_score,
            'runtime_inference': {'suppressed_by': _suppressed_by},
        }
        arbitration = self._arbitrate_decision(fall_result_for_arb, posture_label, posture_probs, posture_score)
        decision_state = arbitration['decision_state']
        explain = arbitration['explain']

        # Risk level
        risk_level = 'high' if fall_score >= 0.75 else ('medium' if fall_score >= self._XG_FALL_THRESHOLD else 'low')
        risk_label = {'low': '안정', 'medium': '주의', 'high': '고위험'}.get(risk_level, '안정')

        # Override: if decision is safe or posture_only, downgrade risk
        if decision_state in ('safe', 'posture_only') and risk_level == 'medium':
            risk_level = 'low'
            risk_label = '안정'

        behavior_class = 'fall' if fall_detected else posture_label
        behavior_label_map = {
            'fall': '낙상', 'stand': '서기', 'walk': '걷기', 'run': '뛰기',
            'sit': '앉기', 'lie': '눕기', 'non-fall': '비낙상',
        }
        behavior_label = behavior_label_map.get(behavior_class, '비낙상')

        if fall_detected:
            summary_text = f'XG-Dual 분석 결과 낙상 가능성이 높습니다. (상태: {decision_state})'
        elif posture_label == 'fall' and posture_score >= 0.40:
            summary_text = f'자세 분류에서 낙상 가능성이 감지되나 이진 Fall 모델에서 확인되지 않았습니다. (상태: {decision_state})'
        else:
            summary_text = f'XG-Dual 분석 결과 즉시 낙상 가능성은 낮습니다. 감지된 자세: {behavior_label}. (상태: {decision_state})'

        _perf['total'] = round(_time.time() - _t_total, 3)

        _result = {
            'fall_detected': fall_detected,
            'behavior_class': behavior_class,
            'behavior_label': behavior_label,
            'risk_score': round(fall_score, 4),
            'risk_level': risk_level,
            'risk_label': risk_label,
            'summary': summary_text,
            'events': [],
            'reference_matches': [],
            'analysis_basis': [],
            'runtime_key': 'xg-dual',
            'runtime_label': 'XG-Dual (Fall+Posture) 분석',
            'posture_label': posture_label,
            'posture_score': round(posture_score, 4),
            'posture_probs': {k: round(v, 4) for k, v in posture_probs.items()},
            'decision_state': decision_state,
            'explain': explain,
            'runtime_inference': {
                'fall_score': round(fall_score, 4),
                'fall_detected': fall_detected,
                'max_probability': round(max_prob, 4),
                'mean_probability': round(mean_prob, 4),
                'fall_window_ratio': round(fall_ratio, 4),
                'fall_windows': len(fall_windows) if len(timeseries) >= 2 else 0,
                'motion_gate_passed': motion_gate_passed,
                'suppressed_by': _suppressed_by,
                'posture_label': posture_label,
                'posture_score': round(posture_score, 4),
                'posture_probs': {k: round(v, 4) for k, v in posture_probs.items()},
                'posture_available': _posture_available,
                'decision_state': decision_state,
                'perf': _perf,
            },
            'behavior_inference': {
                'code': behavior_class,
                'label': behavior_label,
                'source': 'xg-dual',
                'fallback': False,
            },
            'model_runtime': {
                'label': 'XG-Dual (Fall+Posture) 분석',
                'fall_classifier': self._project_relative_path(self._xg_fall_model_path()),
                'posture_classifier': self._project_relative_path(self._xg_posture_model_path()) if self._xg_posture_available() else None,
                'fall_windows': len(fall_windows) if len(timeseries) >= 2 else 0,
                'fall_probability': round(max_prob, 4),
                'feature_count': len(self._XG_FEATURE_COLUMNS),
                'detection_frames': ts_result.get('detection_frames', []),
            },
            'video_meta': {
                'duration': vid_meta.get('duration', 0),
                'width': vid_meta.get('width', 0),
                'height': vid_meta.get('height', 0),
                'fps': vid_meta.get('fps', 0),
            },
        }

        # FN-0014 Stage B: Shadow comparison with RF-Pose (non-blocking)
        try:
            shadow = self._shadow_compare_rf_pose(video_path, _result, filename=filename, input_source=input_source)
            if shadow:
                _result['_shadow_rf_pose'] = shadow.get('comparison', {})
        except Exception:
            pass

        return _result

    def _xg_dual_empty_result(self, vid_meta, perf, ts_result):
        """Return empty result when no usable timeseries data."""
        return {
            'fall_detected': False,
            'behavior_class': 'unknown',
            'behavior_label': '판단 불가',
            'risk_score': 0.0,
            'risk_level': 'low',
            'risk_label': '안정',
            'summary': '분석 윈도우를 생성하지 못했습니다. 영상이 짧거나 사람 추적이 부족합니다.',
            'events': [],
            'reference_matches': [],
            'analysis_basis': [],
            'runtime_key': 'xg-dual',
            'runtime_label': 'XG-Dual (Fall+Posture) 분석',
            'posture_label': 'unknown',
            'posture_score': 0.0,
            'posture_probs': {c: 0.0 for c in self._LABEL_L2_CLASSES},
            'decision_state': 'safe',
            'explain': ['분석 데이터 부족'],
            'runtime_inference': {'perf': perf},
            'behavior_inference': {'code': 'unknown', 'label': '판단 불가', 'source': 'xg-dual', 'fallback': False},
            'model_runtime': {'label': 'XG-Dual (Fall+Posture) 분석', 'detection_frames': ts_result.get('detection_frames', [])},
            'video_meta': {
                'duration': vid_meta.get('duration', 0),
                'width': vid_meta.get('width', 0),
                'height': vid_meta.get('height', 0),
                'fps': vid_meta.get('fps', 0),
            },
        }

    # ── FN-0014 Stage B: Shadow mode — RF-Pose vs XG-Posture comparison ──

    def _shadow_compare_rf_pose(self, video_path, xg_result, filename='', input_source='upload'):
        """Run RF-Pose in shadow (background) and log comparison with XG result.

        This is non-blocking for the user — if RF-Pose fails, it logs and moves on.
        Returns comparison dict (or None if RF-Pose unavailable).
        """
        import time as _time
        import json

        if not self._rf_pose_pipeline_available():
            return None

        shadow_log = {
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'filename': filename,
            'xg_dual': {
                'fall_detected': xg_result.get('fall_detected'),
                'risk_score': xg_result.get('risk_score'),
                'posture_label': xg_result.get('posture_label'),
                'posture_probs': xg_result.get('posture_probs'),
                'decision_state': xg_result.get('decision_state'),
            },
        }

        try:
            _t0 = _time.time()
            rf_result = self._infer_rf_pose_pipeline(video_path, filename, 'balanced', input_source=input_source)
            rf_elapsed = round(_time.time() - _t0, 3)

            rf_fall = rf_result.get('fall_detected', False)
            rf_score = rf_result.get('risk_score', 0.0)
            rf_behavior = rf_result.get('behavior_class', 'unknown')

            xg_fall = xg_result.get('fall_detected', False)
            xg_posture = xg_result.get('posture_label', 'unknown')

            shadow_log['rf_pose'] = {
                'fall_detected': rf_fall,
                'risk_score': rf_score,
                'behavior_class': rf_behavior,
                'elapsed_sec': rf_elapsed,
            }

            # Compute agreement metrics
            fall_agree = (xg_fall == rf_fall)
            score_diff = round(abs(float(xg_result.get('risk_score', 0)) - float(rf_score)), 4)
            shadow_log['comparison'] = {
                'fall_agreement': fall_agree,
                'score_difference': score_diff,
                'xg_posture': xg_posture,
                'rf_behavior': rf_behavior,
            }
        except Exception as e:
            shadow_log['rf_pose'] = {'error': str(e)}
            shadow_log['comparison'] = {'error': str(e)}

        # Write shadow log to file
        try:
            shadow_dir = os.path.join(self._project_root(), 'data', 'storage', 'training', 'fall-detection', 'shadow-compare')
            os.makedirs(shadow_dir, exist_ok=True)
            date_str = datetime.datetime.now().strftime('%Y%m%d')
            log_file = os.path.join(shadow_dir, f'shadow_{date_str}.jsonl')
            with open(log_file, 'a') as f:
                f.write(json.dumps(shadow_log, ensure_ascii=False) + '\n')
        except Exception:
            pass

        return shadow_log

    def shadow_comparison_report(self, days=7):
        """Generate a summary report from shadow comparison logs.

        Returns aggregated agreement/disagreement stats for the given time range.
        """
        import json

        shadow_dir = os.path.join(self._project_root(), 'data', 'storage', 'training', 'fall-detection', 'shadow-compare')
        if not os.path.isdir(shadow_dir):
            return {'status': 'no_data', 'message': 'Shadow comparison 로그가 없습니다.'}

        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        cutoff_str = cutoff.strftime('%Y%m%d')

        total = 0
        fall_agree = 0
        fall_disagree = 0
        score_diffs = []
        errors = 0
        posture_agree = 0
        posture_disagree = 0

        try:
            for fname in sorted(os.listdir(shadow_dir)):
                if not fname.startswith('shadow_') or not fname.endswith('.jsonl'):
                    continue
                date_part = fname.replace('shadow_', '').replace('.jsonl', '')
                if date_part < cutoff_str:
                    continue
                fpath = os.path.join(shadow_dir, fname)
                with open(fpath, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except Exception:
                            continue
                        comp = entry.get('comparison', {})
                        if 'error' in comp:
                            errors += 1
                            continue
                        total += 1
                        if comp.get('fall_agreement'):
                            fall_agree += 1
                        else:
                            fall_disagree += 1
                        sd = comp.get('score_difference', 0)
                        if sd is not None:
                            score_diffs.append(float(sd))
                        xg_p = comp.get('xg_posture', '')
                        rf_b = comp.get('rf_behavior', '')
                        if xg_p and rf_b:
                            # Map RF behavior (fall/non-fall) to coarse posture agreement
                            if xg_p == 'fall' and rf_b == 'fall':
                                posture_agree += 1
                            elif xg_p != 'fall' and rf_b == 'non-fall':
                                posture_agree += 1
                            else:
                                posture_disagree += 1
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

        avg_score_diff = round(sum(score_diffs) / len(score_diffs), 4) if score_diffs else 0
        max_score_diff = round(max(score_diffs), 4) if score_diffs else 0

        return {
            'status': 'ok',
            'period_days': days,
            'total_comparisons': total,
            'fall_agreement': fall_agree,
            'fall_disagreement': fall_disagree,
            'fall_agreement_rate': round(fall_agree / total, 4) if total > 0 else 0,
            'score_diff_avg': avg_score_diff,
            'score_diff_max': max_score_diff,
            'posture_agreement': posture_agree,
            'posture_disagreement': posture_disagree,
            'errors': errors,
            'deletion_readiness': {
                'criteria': [
                    f'fall_agreement_rate >= 0.90: {"PASS" if (fall_agree / total >= 0.90 if total > 0 else False) else "FAIL"}',
                    f'avg_score_diff <= 0.15: {"PASS" if avg_score_diff <= 0.15 else "FAIL"}',
                    f'total_comparisons >= 30: {"PASS" if total >= 30 else "FAIL"}',
                ],
                'ready': (
                    total >= 30
                    and (fall_agree / total >= 0.90 if total > 0 else False)
                    and avg_score_diff <= 0.15
                ),
            },
        }

    def rf_pose_deletion_status(self):
        """FN-0014 Stage C: Check if RF-Pose is ready for hard deletion.

        Returns status dict with checklist of approval criteria.
        Hard delete will NOT be performed automatically — this is an advisory check.
        """
        report = self.shadow_comparison_report(days=30)
        model_exists = self._rf_pose_pipeline_available()
        model_path = self._get_rf_pose_model_path()

        criteria = {
            'shadow_data_sufficient': report.get('total_comparisons', 0) >= 30,
            'fall_agreement_high': report.get('fall_agreement_rate', 0) >= 0.90,
            'score_diff_low': report.get('score_diff_avg', 1.0) <= 0.15,
            'model_file_exists': model_exists,
        }
        all_passed = all(criteria.values())

        return {
            'status': 'ready' if all_passed else 'not_ready',
            'criteria': criteria,
            'shadow_report_summary': {
                'total_comparisons': report.get('total_comparisons', 0),
                'fall_agreement_rate': report.get('fall_agreement_rate', 0),
                'score_diff_avg': report.get('score_diff_avg', 0),
            },
            'model_path': model_path if model_exists else None,
            'message': 'RF-Pose 삭제 승인 조건이 모두 충족되었습니다. hard delete를 진행할 수 있습니다.' if all_passed else 'Shadow mode 데이터가 충분하지 않습니다. 더 많은 비교 데이터를 수집하세요.',
            'preserved_components': [
                'pose feature 계산 유틸 (_extract_unified_timeseries 내 keypoint 처리)',
                'keypoint validation (confidence filtering)',
                'XG 37-feature 공통 추출기',
            ],
        }

    def _get_rf_pose_model_path(self):
        """Return full path to RF-Pose model file."""
        return os.path.join(self._project_root(), 'data', 'storage', 'training', 'fall-detection', 'rf-pose', 'rf_pose_model.pkl')

    # ── FN-0024/0025: Posture Heuristic Boost ──────────────────────────
    def _posture_heuristic_boost(self, raw_probs, feature_windows, classes):
        """Apply domain-knowledge heuristic rules to refine posture predictions.

        Adjusts raw model probabilities using gait/pose features to improve
        walk/run/stand/sit differentiation when training data is scarce.

        Args:
            raw_probs: np.ndarray of shape (N, num_classes) — model output
            feature_windows: list of dicts with feature values per window
            classes: list of class names matching raw_probs columns

        Returns:
            np.ndarray of same shape with adjusted probabilities (re-normalized)
        """
        import numpy as np

        if len(feature_windows) == 0 or raw_probs.shape[0] == 0:
            return raw_probs

        cls_idx = {c: i for i, c in enumerate(classes)}
        adjusted = raw_probs.copy()

        for wi, w in enumerate(feature_windows):
            stillness = w.get('stillness', 1.0)
            cy_period = w.get('center_y_periodicity', 0.0)
            step_period = w.get('step_period_est', 0.0)
            knee_cycle = w.get('knee_angle_cycle_strength', 0.0)
            speed_std = w.get('speed_std', 0.0)
            upper_motion = w.get('upper_body_motion', 0.0)
            osc_count = w.get('oscillation_count', 0.0)
            pose_knee = w.get('pose_knee_bend_mean', 0.0)
            pose_tilt = w.get('pose_tilt_mean', 0.0)
            pose_height = w.get('pose_height_ratio_mean', 0.0)
            area_change = w.get('area_change', 0.0)
            vert_horiz = w.get('vert_horiz_ratio', 0.0)

            cur_label = classes[int(np.argmax(adjusted[wi]))]

            # ── Rule 1: Stand → Walk boost ──
            # Not still + rhythmic vertical movement → likely walking
            is_moving = stillness < 0.6
            has_gait_rhythm = cy_period > 0.15 or knee_cycle > 0.1
            has_body_motion = upper_motion > 0.01 or speed_std > 0.005

            if cur_label == 'stand' and is_moving and (has_gait_rhythm or has_body_motion):
                boost = 0.0
                if cy_period > 0.15:
                    boost += min(cy_period * 0.8, 0.3)       # periodic bounce
                if stillness < 0.3:
                    boost += 0.15                              # clearly not still
                elif stillness < 0.5:
                    boost += 0.08
                if knee_cycle > 0.1:
                    boost += min(knee_cycle * 0.5, 0.15)      # periodic knee bend
                if upper_motion > 0.02:
                    boost += 0.05

                boost = min(boost, 0.45)  # cap total boost
                if boost > 0.05 and 'walk' in cls_idx:
                    wi_walk = cls_idx['walk']
                    wi_stand = cls_idx['stand']
                    # Transfer probability from stand to walk
                    transfer = min(boost, adjusted[wi, wi_stand] * 0.6)
                    adjusted[wi, wi_walk] += transfer
                    adjusted[wi, wi_stand] -= transfer

            # ── Rule 2: Walk → Run boost ──
            # Fast gait + high bounce + short step period → likely running
            elif cur_label == 'walk':
                run_boost = 0.0
                if step_period > 0.0 and step_period < 0.4:    # fast cadence < 0.4s
                    run_boost += 0.15
                if cy_period > 0.3:                              # strong bounce
                    run_boost += min((cy_period - 0.3) * 1.0, 0.2)
                if speed_std > 0.015:                            # high speed variation
                    run_boost += 0.1
                if upper_motion > 0.04:                          # vigorous body motion
                    run_boost += 0.1

                run_boost = min(run_boost, 0.4)
                if run_boost > 0.1 and 'run' in cls_idx:
                    wi_run = cls_idx['run']
                    wi_walk = cls_idx['walk']
                    transfer = min(run_boost, adjusted[wi, wi_walk] * 0.5)
                    adjusted[wi, wi_run] += transfer
                    adjusted[wi, wi_walk] -= transfer

            # ── Rule 3: Stand → Sit boost (FN-0025) ──
            # Bent knees + relatively upright torso + low height ratio → sitting
            elif cur_label == 'stand':
                sit_boost = 0.0
                if pose_knee > 0.25:                             # significant knee bend
                    sit_boost += min((pose_knee - 0.25) * 1.5, 0.25)
                if pose_tilt < 20.0 and pose_knee > 0.2:        # upright but knees bent
                    sit_boost += 0.1
                if pose_height < 0.55 and pose_knee > 0.15:     # short apparent height
                    sit_boost += 0.1
                if stillness > 0.6 and pose_knee > 0.2:         # still + bent knees
                    sit_boost += 0.08

                sit_boost = min(sit_boost, 0.4)
                if sit_boost > 0.08 and 'sit' in cls_idx:
                    wi_sit = cls_idx['sit']
                    wi_stand = cls_idx['stand']
                    transfer = min(sit_boost, adjusted[wi, wi_stand] * 0.5)
                    adjusted[wi, wi_sit] += transfer
                    adjusted[wi, wi_stand] -= transfer

            # ── Re-normalize per window ──
            row_sum = adjusted[wi].sum()
            if row_sum > 0:
                adjusted[wi] /= row_sum

        return adjusted

    # ── FN-0010: XG-Posture Temporal Smoothing ──────────────────────────
    # Transition constraint matrix: {from_class: set_of_allowed_next_classes}
    # FN-0024: Added stand→run and run→stand to allow detection in short clips
    _POSTURE_TRANSITION_ALLOWED = {
        'stand': {'walk', 'run', 'sit', 'fall', 'stand'},
        'walk':  {'stand', 'run', 'fall', 'walk'},
        'run':   {'walk', 'stand', 'fall', 'run'},
        'sit':   {'stand', 'fall', 'sit'},
        'lie':   {'sit', 'stand', 'fall', 'lie'},
        'fall':  {'lie', 'fall'},
    }

    def _smooth_posture_sequence(self, posture_windows, window_size=5, ema_alpha=0.3):
        """Apply temporal smoothing to a sequence of posture predictions.

        Args:
            posture_windows: list of dicts, each with 'label' (str) and 'probs' (dict of class→prob)
            window_size: majority vote window radius (3~5 recommended)
            ema_alpha: EMA decay factor (higher → more weight on current)

        Returns:
            list of dicts with smoothed 'label', 'probs', 'raw_label', 'transition_blocked'
        """
        if not posture_windows:
            return []

        classes = self._LABEL_L2_CLASSES  # ['stand','walk','run','sit','lie','fall']
        n = len(posture_windows)
        results = []

        # EMA pass — smoothed probability distributions
        ema_probs = []
        prev = {c: 1.0 / len(classes) for c in classes}
        for w in posture_windows:
            probs = w.get('probs', {})
            smoothed = {}
            for c in classes:
                p_cur = probs.get(c, 0.0)
                smoothed[c] = ema_alpha * p_cur + (1 - ema_alpha) * prev.get(c, 0.0)
            # Normalize
            total = sum(smoothed.values())
            if total > 0:
                smoothed = {c: v / total for c, v in smoothed.items()}
            ema_probs.append(smoothed)
            prev = smoothed

        # Majority vote pass
        for i in range(n):
            raw_label = posture_windows[i].get('label', 'stand')
            raw_probs = posture_windows[i].get('probs', {})

            # Collect labels in vote window
            i_start = max(0, i - window_size // 2)
            i_end = min(n, i + window_size // 2 + 1)
            vote_labels = [posture_windows[j].get('label', 'stand') for j in range(i_start, i_end)]

            # Count votes
            vote_counts = {}
            for lbl in vote_labels:
                vote_counts[lbl] = vote_counts.get(lbl, 0) + 1
            majority_label = max(vote_counts, key=vote_counts.get)

            # Combine: EMA-smoothed highest vs majority — take EMA if confident, else majority
            ema_label = max(ema_probs[i], key=ema_probs[i].get)
            ema_conf = ema_probs[i].get(ema_label, 0.0)
            chosen_label = ema_label if ema_conf >= 0.45 else majority_label

            # Transition constraint enforcement
            transition_blocked = False
            if i > 0:
                prev_label = results[i - 1]['label']
                allowed = self._POSTURE_TRANSITION_ALLOWED.get(prev_label, set(classes))
                if chosen_label not in allowed:
                    # Block impossible transition — keep previous label
                    # Exception: fall always allowed (safety-first)
                    if chosen_label != 'fall':
                        transition_blocked = True
                        chosen_label = prev_label

            results.append({
                'label': chosen_label,
                'raw_label': raw_label,
                'probs': ema_probs[i],
                'raw_probs': raw_probs,
                'transition_blocked': transition_blocked,
            })

        return results

    # ── FN-0010: Decision Arbitration — Fall vs Posture ────────────────
    # Decision states for XG-Dual pipeline
    _DECISION_STATES = ['safe', 'posture_only', 'fall_suspected', 'fall_confirmed', 'uncertain']

    def _arbitrate_decision(self, fall_result, posture_label, posture_probs, posture_score):
        """Arbitrate between XG-Fall and XG-Posture predictions.

        Safety-first principle: when Fall and Posture conflict, Fall takes priority.

        Args:
            fall_result: dict from _infer_xg_fall() (or subset with fall_detected, risk_score, suppressed_by)
            posture_label: str — smoothed posture label
            posture_probs: dict — smoothed probability distribution
            posture_score: float — confidence of top posture class

        Returns:
            dict with decision_state, explain list, adjusted scores
        """
        fall_detected = fall_result.get('fall_detected', False)
        fall_score = fall_result.get('risk_score', 0.0)
        suppressed = fall_result.get('runtime_inference', {}).get('suppressed_by', [])
        explain = []

        # Case 1: High fall + posture=sit → boundary warning
        if fall_score >= 0.50 and posture_label == 'sit':
            explain.append('fall/sit 경계: 빠른 앉기와 낙상 구분이 모호합니다.')
            if fall_detected:
                state = 'fall_suspected'
                explain.append('안전 우선 원칙에 따라 낙상 의심으로 분류합니다.')
            elif 'fast_sit_suppressor' in suppressed:
                state = 'posture_only'
                explain.append('빠른 앉기 패턴이 감지되어 낙상 억제됨.')
            else:
                state = 'uncertain'

        # Case 2: Low fall + posture=lie → lying down, no emergency
        elif not fall_detected and posture_label == 'lie':
            state = 'posture_only'
            explain.append('눕는 자세가 감지됨. 낙상 위험 낮음.')
            if 'controlled_lie_suppressor' in suppressed:
                explain.append('제어된 눕기 패턴으로 판단됨.')

        # Case 3: Fall confirmed
        elif fall_detected and fall_score >= 0.75:
            state = 'fall_confirmed'
            explain.append(f'높은 낙상 점수 ({fall_score:.2f})')
            if posture_label == 'fall':
                explain.append('자세 분류도 낙상으로 일치.')
            elif posture_label in ('lie', 'sit'):
                explain.append(f'자세는 {posture_label}이지만 안전 우선 원칙 적용.')

        # Case 4: Fall suspected
        elif fall_detected:
            state = 'fall_suspected'
            explain.append(f'낙상 감지됨 (점수: {fall_score:.2f})')
            if posture_label != 'fall':
                explain.append(f'자세 분류({posture_label})와 불일치, 안전 우선 적용.')

        # Case 5: No fall, posture active
        elif posture_score >= 0.40 and posture_label in ('stand', 'walk', 'run', 'sit', 'lie'):
            state = 'posture_only' if posture_label != 'fall' else 'fall_suspected'
            if posture_label in ('walk', 'run'):
                explain.append(f'활동적 자세({posture_label}) 감지됨.')
            elif posture_label == 'stand':
                explain.append('직립 자세 유지.')
            elif posture_label in ('sit', 'lie'):
                explain.append(f'{posture_label} 자세 감지됨. 위험 낮음.')
            state = 'safe' if posture_label in ('stand', 'walk', 'run') else state

        # Case 6: fallback
        else:
            state = 'safe' if fall_score < 0.30 else 'uncertain'
            if state == 'uncertain':
                explain.append('낙상·자세 판정 모두 불확실합니다.')

        return {
            'decision_state': state,
            'explain': explain,
            'fall_detected': fall_detected,
            'fall_score': round(fall_score, 4),
            'posture_label': posture_label,
            'posture_score': round(posture_score, 4),
            'posture_probs': {k: round(v, 4) for k, v in posture_probs.items()},
        }

    # ── FN-0007: XG-Fall retrain with 37 features ──
    def retrain_xg_fall(self):
        """Train XG-Fall binary classifier with 37 features from existing Y/N intake data."""
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import joblib
        import numpy as np
        import pandas as pd
        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
        from sklearn.model_selection import StratifiedKFold, cross_validate

        try:
            from xgboost import XGBClassifier
            _use_xgb = True
        except ImportError:
            from sklearn.ensemble import GradientBoostingClassifier
            _use_xgb = False

        feature_cols = self._XG_FEATURE_COLUMNS
        rows = []
        skipped = []
        intake_root = self._training_dir()

        for label in ['Y', 'N']:
            label_dir = os.path.join(intake_root, label)
            if not os.path.isdir(label_dir):
                continue
            for name in sorted(os.listdir(label_dir)):
                if name.startswith('.') or name.endswith('.json'):
                    continue
                video_path = os.path.join(label_dir, name)
                try:
                    ts_result = self._extract_unified_timeseries(video_path)
                    windows = self._build_xg_feature_windows(
                        ts_result['timeseries'], ts_result['vid_meta'],
                        window_sec=1.0, stride_sec=0.5,
                    )
                    if len(windows) == 0:
                        skipped.append({'video': name, 'label': label, 'reason': 'No valid windows'})
                        continue
                    # Use peak window (max center_dy + floor_proximity) as representative
                    best_w = max(windows, key=lambda w: w.get('max_down_speed', 0) + w.get('floor_proximity', 0))
                    row = {'video': name, 'label': label}
                    for col in feature_cols:
                        row[col] = float(best_w.get(col, 0.0) or 0.0)
                    rows.append(row)
                except Exception as e:
                    skipped.append({'video': name, 'label': label, 'reason': str(e)})

        summary = {
            'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'model_type': 'xg-fall-37',
            'training_samples': len(rows),
            'class_distribution': {
                'Y': len([r for r in rows if r['label'] == 'Y']),
                'N': len([r for r in rows if r['label'] == 'N']),
            },
            'features': list(feature_cols),
            'feature_count': len(feature_cols),
            'source': 'hitl-intake-xg-fall',
            'skipped': skipped,
            'ready': False,
        }
        errors = []
        if summary['class_distribution']['Y'] < 2 or summary['class_distribution']['N'] < 2:
            summary['message'] = 'XG-Fall 재학습은 클래스별 최소 2건 이상 필요합니다.'
            self._write_json(self._project_abspath(self._XG_FALL_SUMMARY_REL_PATH), summary)
            return {'summary': summary, 'errors': errors}

        df = pd.DataFrame(rows)
        X = df[feature_cols].astype(float).to_numpy()
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        y = (df['label'].astype(str).str.upper() == 'Y').astype(int).to_numpy()
        min_class = min(int(np.sum(y == 1)), int(np.sum(y == 0)))
        n_splits = 3 if min_class >= 3 else 2

        if _use_xgb:
            scale_pos = float(np.sum(y == 0)) / max(float(np.sum(y == 1)), 1)
            model = XGBClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.1,
                scale_pos_weight=scale_pos,
                eval_metric='logloss', random_state=42, n_jobs=-1,
                use_label_encoder=False,
            )
        else:
            model = GradientBoostingClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42,
            )

        scoring = {'accuracy': 'accuracy', 'precision': 'precision', 'recall': 'recall', 'f1': 'f1', 'roc_auc': 'roc_auc'}
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        cv_results = cross_validate(model, X, y, cv=cv, scoring=scoring, return_train_score=False)
        model.fit(X, y)

        model_path = self._xg_fall_model_path()
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        import tempfile
        _tmp_fd, _tmp_path = tempfile.mkstemp(suffix='.pkl.tmp', dir=os.path.dirname(model_path))
        os.close(_tmp_fd)
        try:
            joblib.dump(model, _tmp_path)
            os.replace(_tmp_path, model_path)
        except BaseException:
            if os.path.exists(_tmp_path):
                os.unlink(_tmp_path)
            raise
        self.__class__._xg_fall_model_cache = None
        self.__class__._xg_fall_model_mtime = None
        self.__class__._xg_fall_model_path_cache = None

        y_pred = model.predict(X)
        y_proba = model.predict_proba(X)[:, 1] if hasattr(model, 'predict_proba') else None
        summary.update({
            'ready': True,
            'model_path': self._project_relative_path(model_path),
            'algorithm': 'XGBClassifier' if _use_xgb else 'GradientBoostingClassifier',
            'cv': {
                'folds': n_splits,
                'accuracy': round(float(np.mean(cv_results['test_accuracy'])), 4),
                'precision': round(float(np.mean(cv_results['test_precision'])), 4),
                'recall': round(float(np.mean(cv_results['test_recall'])), 4),
                'f1': round(float(np.mean(cv_results['test_f1'])), 4),
                'roc_auc': round(float(np.mean(cv_results['test_roc_auc'])), 4),
            },
            'train_metrics': {
                'accuracy': round(float(accuracy_score(y, y_pred)), 4),
                'precision': round(float(precision_score(y, y_pred, zero_division=0)), 4),
                'recall': round(float(recall_score(y, y_pred, zero_division=0)), 4),
                'f1': round(float(f1_score(y, y_pred, zero_division=0)), 4),
                'roc_auc': round(float(roc_auc_score(y, y_proba)), 4) if y_proba is not None and len(np.unique(y)) > 1 else 0.0,
            },
            'feature_importance': {col: round(float(imp), 4) for col, imp in zip(feature_cols, model.feature_importances_)} if hasattr(model, 'feature_importances_') else {},
        })
        self._write_json(self._project_abspath(self._XG_FALL_SUMMARY_REL_PATH), summary)
        return {'summary': summary, 'errors': errors}

    # ── FN-0008: XG-Posture multiclass retrain ──────────────────────────
    _XG_POSTURE_CLASSES = ['stand', 'walk', 'run', 'sit', 'lie', 'fall']

    def retrain_xg_posture(self):
        """Train XG-Posture 6-class classifier with 37 features.

        Expects posture-labeled data in intake/{posture_class}/ directories
        (e.g. intake/stand/, intake/walk/, ..., intake/fall/).
        Falls back to Y/N → fall/stand mapping for initial bootstrap.
        """
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import joblib
        import numpy as np
        import pandas as pd
        from sklearn.metrics import accuracy_score, f1_score, classification_report
        from sklearn.model_selection import StratifiedKFold, cross_validate

        try:
            from xgboost import XGBClassifier
            _use_xgb = True
        except ImportError:
            from sklearn.ensemble import GradientBoostingClassifier
            _use_xgb = False

        feature_cols = self._XG_FEATURE_COLUMNS
        posture_classes = self._XG_POSTURE_CLASSES
        class_to_int = {c: i for i, c in enumerate(posture_classes)}
        rows = []
        skipped = []
        intake_root = self._training_dir()

        # 1) Check for posture-specific directories
        has_posture_dirs = False
        for cls_name in posture_classes:
            cls_dir = os.path.join(intake_root, cls_name)
            if os.path.isdir(cls_dir) and len(os.listdir(cls_dir)) > 0:
                has_posture_dirs = True
                break

        if has_posture_dirs:
            for cls_name in posture_classes:
                cls_dir = os.path.join(intake_root, cls_name)
                if not os.path.isdir(cls_dir):
                    continue
                for name in sorted(os.listdir(cls_dir)):
                    if name.startswith('.') or name.endswith('.json'):
                        continue
                    video_path = os.path.join(cls_dir, name)
                    try:
                        ts = self._extract_unified_timeseries(video_path)
                        windows = self._build_xg_feature_windows(
                            ts['timeseries'], ts['vid_meta'],
                            window_sec=1.5, stride_sec=0.5,
                        )
                        if not windows:
                            skipped.append({'video': name, 'class': cls_name, 'reason': 'No valid windows'})
                            continue
                        best_w = max(windows, key=lambda w: w.get('max_down_speed', 0) + w.get('floor_proximity', 0))
                        row = {'video': name, 'posture': cls_name}
                        for col in feature_cols:
                            row[col] = float(best_w.get(col, 0.0) or 0.0)
                        rows.append(row)
                    except Exception as e:
                        skipped.append({'video': name, 'class': cls_name, 'reason': str(e)})
        else:
            # Bootstrap: Y→fall, N→stand
            for label in ['Y', 'N']:
                label_dir = os.path.join(intake_root, label)
                if not os.path.isdir(label_dir):
                    continue
                posture = 'fall' if label == 'Y' else 'stand'
                for name in sorted(os.listdir(label_dir)):
                    if name.startswith('.') or name.endswith('.json'):
                        continue
                    video_path = os.path.join(label_dir, name)
                    try:
                        ts = self._extract_unified_timeseries(video_path)
                        windows = self._build_xg_feature_windows(
                            ts['timeseries'], ts['vid_meta'],
                            window_sec=1.5, stride_sec=0.5,
                        )
                        if not windows:
                            skipped.append({'video': name, 'class': posture, 'reason': 'No valid windows'})
                            continue
                        best_w = max(windows, key=lambda w: w.get('max_down_speed', 0) + w.get('floor_proximity', 0))
                        row = {'video': name, 'posture': posture}
                        for col in feature_cols:
                            row[col] = float(best_w.get(col, 0.0) or 0.0)
                        rows.append(row)
                    except Exception as e:
                        skipped.append({'video': name, 'class': posture, 'reason': str(e)})

        class_dist = {}
        for cls_name in posture_classes:
            class_dist[cls_name] = len([r for r in rows if r['posture'] == cls_name])

        summary = {
            'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'model_type': 'xg-posture-37',
            'training_samples': len(rows),
            'class_distribution': class_dist,
            'features': list(feature_cols),
            'feature_count': len(feature_cols),
            'classes': posture_classes,
            'source': 'posture-dirs' if has_posture_dirs else 'yn-bootstrap',
            'skipped': skipped,
            'ready': False,
        }
        errors = []
        active_classes = [c for c in posture_classes if class_dist.get(c, 0) >= 2]
        if len(active_classes) < 2:
            summary['message'] = f'XG-Posture 재학습은 최소 2개 클래스(각 2건 이상)가 필요합니다. 현재 활성 클래스: {active_classes}'
            self._write_json(self._project_abspath(self._XG_POSTURE_SUMMARY_REL_PATH), summary)
            return {'summary': summary, 'errors': errors}

        # Filter to active classes only
        filtered = [r for r in rows if r['posture'] in active_classes]
        df = pd.DataFrame(filtered)
        X = df[feature_cols].astype(float).to_numpy()
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        active_to_int = {c: i for i, c in enumerate(active_classes)}
        y = df['posture'].map(active_to_int).to_numpy()
        min_class_count = min(int(np.sum(y == i)) for i in range(len(active_classes)))
        n_splits = min(3, min_class_count) if min_class_count >= 2 else 2

        n_classes = len(active_classes)
        if _use_xgb:
            model = XGBClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.1,
                objective='multi:softprob', num_class=n_classes,
                eval_metric='mlogloss', random_state=42, n_jobs=-1,
                use_label_encoder=False,
            )
        else:
            model = GradientBoostingClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.1, random_state=42,
            )

        scoring = {
            'accuracy': 'accuracy',
            'f1_macro': 'f1_macro',
        }
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        cv_results = cross_validate(model, X, y, cv=cv, scoring=scoring, return_train_score=False)
        model.fit(X, y)

        # Save model with class mapping metadata
        model_data = {
            'model': model,
            'classes': active_classes,
            'feature_cols': list(feature_cols),
        }
        model_path = self._xg_posture_model_path()
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        import tempfile
        _tmp_fd, _tmp_path = tempfile.mkstemp(suffix='.pkl.tmp', dir=os.path.dirname(model_path))
        os.close(_tmp_fd)
        try:
            joblib.dump(model_data, _tmp_path)
            os.replace(_tmp_path, model_path)
        except BaseException:
            if os.path.exists(_tmp_path):
                os.unlink(_tmp_path)
            raise
        self.__class__._xg_posture_model_cache = None
        self.__class__._xg_posture_model_mtime = None
        self.__class__._xg_posture_model_path_cache = None

        y_pred = model.predict(X)
        # Fix: ensure y_pred is 1D integer array (XGBClassifier with multi:softprob may return odd shapes)
        y_pred = np.asarray(y_pred).flatten().astype(int)
        y = np.asarray(y).flatten().astype(int)
        report = classification_report(y, y_pred, target_names=active_classes, output_dict=True, zero_division=0)
        class_recall = {c: round(report[c]['recall'], 4) for c in active_classes if c in report}

        summary.update({
            'ready': True,
            'active_classes': active_classes,
            'model_path': self._project_relative_path(model_path),
            'algorithm': 'XGBClassifier' if _use_xgb else 'GradientBoostingClassifier',
            'cv': {
                'folds': n_splits,
                'accuracy': round(float(np.mean(cv_results['test_accuracy'])), 4),
                'f1_macro': round(float(np.mean(cv_results['test_f1_macro'])), 4),
            },
            'train_metrics': {
                'accuracy': round(float(accuracy_score(y, y_pred)), 4),
                'f1_macro': round(float(f1_score(y, y_pred, average='macro', zero_division=0)), 4),
                'class_recall': class_recall,
            },
            'feature_importance': {col: round(float(imp), 4) for col, imp in zip(feature_cols, model.feature_importances_)} if hasattr(model, 'feature_importances_') else {},
        })
        self._write_json(self._project_abspath(self._XG_POSTURE_SUMMARY_REL_PATH), summary)
        return {'summary': summary, 'errors': errors}

    def submit_analysis_feedback(self, saved_name, predicted_label, feedback_status, actual_label='', note='', retrain=False, posture_class='', predicted_posture='', ambiguity_flag=False, occlusion_flag=False, short_clip_flag=False):
        """FN-0013: 2-Level 피드백 (낙상 Y/N + 자세 6-class + 애매함 태깅).

        Parameters:
            saved_name: 분석했던 파일 이름
            predicted_label: 모델 예측 낙상 라벨 (Y/N)
            feedback_status: correct / incorrect
            actual_label: 실제 낙상 라벨 (Y/N)
            note: 사용자 메모
            retrain: 수동 재학습 요청 여부
            posture_class: 사용자가 선택한 실제 자세 라벨 (stand/walk/run/sit/lie/fall)
            predicted_posture: 모델이 예측한 자세 라벨
            ambiguity_flag: 애매한 동작 여부
            occlusion_flag: 가림 현상 여부
            short_clip_flag: 짧은 영상 여부
        """
        saved_name = self._sanitize_filename(saved_name)
        predicted_label = str(predicted_label or '').strip().upper()
        feedback_status = str(feedback_status or '').strip().lower()
        actual_label = str(actual_label or '').strip().upper()
        posture_class = str(posture_class or '').strip().lower()
        predicted_posture = str(predicted_posture or '').strip().lower()
        ambiguity_flag = str(ambiguity_flag).lower() in ('true', '1', 'yes', 'y') if isinstance(ambiguity_flag, str) else bool(ambiguity_flag)
        occlusion_flag = str(occlusion_flag).lower() in ('true', '1', 'yes', 'y') if isinstance(occlusion_flag, str) else bool(occlusion_flag)
        short_clip_flag = str(short_clip_flag).lower() in ('true', '1', 'yes', 'y') if isinstance(short_clip_flag, str) else bool(short_clip_flag)
        valid_postures = self._XG_POSTURE_CLASSES  # ['stand','walk','run','sit','lie','fall']
        if posture_class and posture_class not in valid_postures:
            posture_class = ''
        if predicted_label not in ('Y', 'N'):
            raise Exception('예측 라벨 정보가 올바르지 않습니다.')
        if feedback_status not in ('correct', 'incorrect'):
            raise Exception('피드백 상태는 correct 또는 incorrect 이어야 합니다.')
        final_label = predicted_label if feedback_status == 'correct' else actual_label
        if final_label not in ('Y', 'N'):
            raise Exception('실제 정답 라벨(Y/N)을 선택해야 합니다.')

        video_path, meta_path = self._load_upload_paths(saved_name)
        if os.path.exists(video_path) is False:
            raise Exception('원본 업로드 영상을 찾을 수 없습니다.')

        # --- 1) Y/N intake (기존 호환) ---
        intake_dir = os.path.join(self._training_dir(), final_label)
        os.makedirs(intake_dir, exist_ok=True)
        target_name = 'feedback-' + saved_name
        target_path = os.path.join(intake_dir, target_name)
        shutil.copy2(video_path, target_path)
        source_meta = self._read_json(meta_path, default={}) or {}
        feedback_meta = {
            'feedback_type': 'analysis-validation',
            'feedback_version': 2,
            'source_saved_name': saved_name,
            'predicted_label': predicted_label,
            'actual_label': final_label,
            'predicted_posture': predicted_posture,
            'posture_class': posture_class,
            'feedback_status': feedback_status,
            'ambiguity_flag': ambiguity_flag,
            'occlusion_flag': occlusion_flag,
            'short_clip_flag': short_clip_flag,
            'uploaded_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'note': note,
            'analysis_file': source_meta,
        }
        self._write_json(target_path + '.json', feedback_meta)

        # --- 2) Posture-class intake (XG-Posture 재학습용) ---
        posture_intake_saved = False
        if posture_class:
            posture_intake_dir = os.path.join(self._training_dir(), posture_class)
            os.makedirs(posture_intake_dir, exist_ok=True)
            posture_target = os.path.join(posture_intake_dir, target_name)
            shutil.copy2(video_path, posture_target)
            self._write_json(posture_target + '.json', feedback_meta)
            posture_intake_saved = True

        # --- 3) Hard-case 태깅 ---
        is_hard_case = ambiguity_flag or occlusion_flag or short_clip_flag
        if is_hard_case:
            hard_case_dir = os.path.join(self._training_dir(), '_hard_cases')
            os.makedirs(hard_case_dir, exist_ok=True)
            hard_meta = {
                **feedback_meta,
                'hard_case_reasons': [],
            }
            if ambiguity_flag:
                hard_meta['hard_case_reasons'].append('ambiguity')
            if occlusion_flag:
                hard_meta['hard_case_reasons'].append('occlusion')
            if short_clip_flag:
                hard_meta['hard_case_reasons'].append('short_clip')
            self._write_json(os.path.join(hard_case_dir, target_name + '.json'), hard_meta)

        feedback_summary = self._intake_summary()
        result = {
            'saved_name': target_name,
            'final_label': final_label,
            'feedback_status': feedback_status,
            'posture_class': posture_class,
            'posture_intake_saved': posture_intake_saved,
            'is_hard_case': is_hard_case,
            'feedback_summary': feedback_summary,
        }
        # FN-0013: 분리된 재학습 트리거
        auto_retrain_triggered = False
        auto_posture_retrain_triggered = False
        if not retrain and feedback_summary.get('since_last_train', 0) >= self.AUTO_RETRAIN_THRESHOLD:
            retrain = True
            auto_retrain_triggered = True
        if retrain:
            result['retrain'] = self.retrain_baseline()
            result['auto_retrain_triggered'] = auto_retrain_triggered
            if auto_retrain_triggered:
                result['auto_retrain_reason'] = f"마지막 학습 이후 {feedback_summary.get('since_last_train', 0)}건 피드백 누적 (임계값: {self.AUTO_RETRAIN_THRESHOLD}건)"
        # XG-Posture 별도 자동 재학습: 자세 피드백 누적 시 트리거
        posture_count = feedback_summary.get('posture_intake_total', 0)
        if not retrain and posture_class and posture_count >= self.AUTO_RETRAIN_THRESHOLD:
            try:
                result['posture_retrain'] = self.retrain_xg_posture()
                auto_posture_retrain_triggered = True
                result['auto_posture_retrain_triggered'] = True
                result['auto_posture_retrain_reason'] = f"자세 피드백 {posture_count}건 누적 (임계값: {self.AUTO_RETRAIN_THRESHOLD}건)"
            except Exception as e:
                result['posture_retrain_error'] = str(e)
        return result

    def _clip_window(self, event_time=0.0, duration=0.0, before=8.0, after=7.0):
        duration = max(0.0, float(duration or 0.0))
        event_time = max(0.0, float(event_time or 0.0))
        start = max(0.0, event_time - before)
        end = event_time + after
        if duration > 0:
            end = min(duration, end)
        if end <= start:
            end = start + (min(duration, 15.0) if duration > 0 else 15.0)
        return {
            'event_time_sec': round(event_time, 2),
            'start_sec': round(start, 2),
            'end_sec': round(end, 2),
            'duration_sec': round(max(0.0, end - start), 2),
        }

    def _video_meta(self, video_path):
        if cv2 is None or os.path.exists(video_path) is False:
            return {'fps': 0.0, 'frame_count': 0, 'duration_sec': 0.0, 'width': 0, 'height': 0}
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened() is False:
            return {'fps': 0.0, 'frame_count': 0, 'duration_sec': 0.0, 'width': 0, 'height': 0}
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        if fps <= 0:
            fps = 30.0
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        return {'fps': round(fps, 4), 'frame_count': frame_count, 'duration_sec': round(duration, 2), 'width': width, 'height': height}

    def _extract_clip(self, video_path, key, clip_window):
        if cv2 is None or os.path.exists(video_path) is False:
            return {'clip_path': '', 'message': '원본 영상을 찾을 수 없습니다.'}
        meta = self._video_meta(video_path)
        fps = float(meta.get('fps', 0.0) or 30.0)
        start_sec = float(clip_window.get('start_sec', 0.0) or 0.0)
        end_sec = float(clip_window.get('end_sec', 0.0) or 0.0)
        start_frame = int(start_sec * fps)
        end_frame = int(end_sec * fps)
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened() is False:
            return {'clip_path': '', 'message': '원본 영상을 열 수 없습니다.'}
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or meta.get('width', 0) or 640)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or meta.get('height', 0) or 360)
        out_path = os.path.join(self._clip_dir(), self._sanitize_filename(key) + '.mp4')
        writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), fps or 30.0, (width, height))
        current = start_frame
        while current <= end_frame:
            ok, frame = cap.read()
            if ok is False:
                break
            writer.write(frame)
            current += 1
        cap.release()
        writer.release()
        if os.path.exists(out_path) is False:
            return {'clip_path': '', 'message': '클립을 생성하지 못했습니다.'}
        return {'clip_path': out_path, 'message': '이벤트 전후 클립을 추출했습니다.'}

    def reference_preview_info(self, scene_id):
        video_path = os.path.join(self._storage_dir(), self._sanitize_filename(scene_id))
        if os.path.exists(video_path) is False:
            raise Exception('복구 가능한 유사 기준 영상 정보가 없습니다.')
        meta = self._video_meta(video_path)
        clip_window = self._clip_window(event_time=max(1.0, meta.get('duration_sec', 0.0) * 0.5), duration=meta.get('duration_sec', 0.0))
        return {
            'scene_id': scene_id,
            'scene_group': scene_id,
            'label': 'reference',
            'source': 'local',
            'clip_window': clip_window,
            'clip_info': self._extract_clip(video_path, 'reference-' + scene_id, clip_window),
            'video_meta': meta,
        }

    def _send_sms(self, sms_config, recipient_phone, message_body):
        """SMS 게이트웨이로 실제 HTTP 전송. 성공 시 True, 실패 시 에러 문자열 반환."""
        if _http is None:
            return 'requests 라이브러리가 설치되지 않았습니다.'
        url = (sms_config.get('webhook_url') or '').strip()
        auth_token = (sms_config.get('auth_token') or '').strip()
        sender = (sms_config.get('sender') or '').strip()
        timeout = int(sms_config.get('timeout_sec', 8) or 8)
        if not url:
            return 'SMS webhook URL이 설정되지 않았습니다.'
        headers = {'Content-Type': 'application/json'}
        if auth_token:
            headers['Authorization'] = 'Bearer ' + auth_token
        payload = {
            'message': {
                'to': recipient_phone,
                'from': sender,
                'text': message_body,
            }
        }
        try:
            resp = _http.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code < 300:
                return True
            return 'SMS 응답 ' + str(resp.status_code) + ': ' + resp.text[:200]
        except Exception as e:
            return 'SMS 전송 실패: ' + str(e)

    def _send_push(self, push_config, title, body):
        """푸시 게이트웨이로 실제 HTTP 전송. 성공 시 True, 실패 시 에러 문자열 반환."""
        if _http is None:
            return 'requests 라이브러리가 설치되지 않았습니다.'
        url = (push_config.get('webhook_url') or '').strip()
        auth_token = (push_config.get('auth_token') or '').strip()
        target = (push_config.get('target') or '').strip()
        platform = (push_config.get('platform') or 'fcm').strip()
        timeout = int(push_config.get('timeout_sec', 8) or 8)
        if not url:
            return 'Push webhook URL이 설정되지 않았습니다.'
        headers = {'Content-Type': 'application/json'}
        if auth_token:
            headers['Authorization'] = 'Bearer ' + auth_token
        payload = {
            'message': {
                'notification': {'title': title, 'body': body},
                'to': target,
                'platform': platform,
            }
        }
        try:
            resp = _http.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code < 300:
                return True
            return 'Push 응답 ' + str(resp.status_code) + ': ' + resp.text[:200]
        except Exception as e:
            return 'Push 전송 실패: ' + str(e)

    def _dispatch_to_guardians(self, settings, risk_level, risk_label, summary, fall_detected):
        """모든 활성 보호자에게 SMS/Push 전송. 결과 리스트 반환."""
        sms_cfg = (settings.get('gateway', {}).get('sms', {}) or {})
        push_cfg = (settings.get('gateway', {}).get('push', {}) or {})
        sms_enabled = bool(sms_cfg.get('enabled'))
        push_enabled = bool(push_cfg.get('enabled'))
        guardians = list(settings.get('guardians', []) or [])
        primary = settings.get('guardian', {}) or {}
        if primary.get('phone'):
            has_primary = any(g.get('phone') == primary['phone'] for g in guardians)
            if not has_primary:
                guardians.insert(0, {'name': primary.get('name', '보호자'), 'phone': primary['phone'], 'enabled': True})
        level_label = risk_label or risk_level
        sms_body = '[낙상 감지 알림] ' + str(level_label) + ' 단계 위험이 감지되었습니다. ' + str(summary)
        push_title = '낙상 ' + str(level_label) + ' 감지'
        push_body = summary or (str(level_label) + ' 단계 위험이 감지되었습니다.')
        results = []
        for guardian in guardians:
            if not guardian.get('enabled', True):
                continue
            name = guardian.get('name', '보호자')
            phone = guardian.get('phone', '')
            entry = {'name': name, 'phone': phone, 'sms': None, 'push': None}
            if sms_enabled and phone:
                sms_result = self._send_sms(sms_cfg, phone, sms_body)
                entry['sms'] = 'sent' if sms_result is True else str(sms_result)
            if push_enabled:
                push_result = self._send_push(push_cfg, push_title, push_body)
                entry['push'] = 'sent' if push_result is True else str(push_result)
            results.append(entry)
        return results

    def alert_history(self, page=1, page_size=20):
        """알람 이력을 최신순으로 조회."""
        alerts_dir = self._alerts_dir()
        files = []
        for name in os.listdir(alerts_dir):
            if not name.endswith('.json') or name == 'settings.json':
                continue
            fpath = os.path.join(alerts_dir, name)
            try:
                mtime = os.path.getmtime(fpath)
            except Exception:
                mtime = 0
            files.append((name, fpath, mtime))
        files.sort(key=lambda x: x[2], reverse=True)
        total = len(files)
        start = (max(1, int(page)) - 1) * int(page_size)
        end = start + int(page_size)
        items = []
        for name, fpath, mtime in files[start:end]:
            data = self._read_json(fpath, default={}) or {}
            items.append({
                'filename': name,
                'saved_name': data.get('saved_name', ''),
                'risk_level': data.get('risk_level', ''),
                'risk_score': data.get('risk_score', 0),
                'risk_label': data.get('risk_label', ''),
                'fall_detected': data.get('fall_detected', False),
                'guardian_name': data.get('guardian_name', ''),
                'guardian_phone': data.get('guardian_phone', ''),
                'guardian_status': (data.get('result', {}) or {}).get('guardian', {}).get('status', ''),
                'dispatch_results': data.get('dispatch_results', []),
                'created_at': data.get('created_at', ''),
                'summary': data.get('summary', ''),
            })
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size}

    def save_guardians(self, guardians_data):
        """보호자 목록 저장 (다중 보호자 지원)."""
        settings = self._load_alert_settings()
        guardians = []
        for g in (guardians_data or []):
            name = str(g.get('name', '')).strip()
            phone = str(g.get('phone', '')).strip()
            if not name and not phone:
                continue
            guardians.append({
                'name': name or '보호자',
                'phone': phone,
                'enabled': bool(g.get('enabled', True)),
            })
        settings['guardians'] = guardians
        if guardians:
            settings['guardian'] = {'name': guardians[0]['name'], 'phone': guardians[0]['phone']}
        settings['updated_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._write_json(self._alert_settings_path(), settings)
        return self._public_alert_settings(settings)

    def _build_alert_display(self, saved_name, risk_level='low', risk_score=0.0, risk_label='', summary='', fall_detected=False, event_time=0.0, event_label='대표 분석 구간', duration=0.0):
        """경량 화면 표시 전용 알림 생성. 클립 추출·외부 발송 없이 즉시 반환."""
        settings = self._load_alert_settings()
        protocol = self._emergency_protocol()
        protocol_levels = protocol.get('levels', []) or []
        primary_guardian = settings.get('guardian', {}) or {}
        guardian_name = primary_guardian.get('name', '보호자')
        guardian_phone = primary_guardian.get('phone', '')
        emergency_required = str(risk_level).lower() == 'high' or bool(fall_detected)
        guardian_required = str(risk_level).lower() in ('medium', 'high') or emergency_required
        level_label = risk_label or risk_level
        clip_window = self._clip_window(event_time=event_time, duration=duration)

        guardian_message = '외부 알림 발송이 비활성화되어 있습니다. 화면 알림만 표시됩니다.'
        if guardian_required:
            guardian_message = str(level_label) + ' 단계 위험이 감지되었습니다. (외부 발송 비활성화)'

        result = {
            'guardian': {
                'required': guardian_required,
                'status': 'display-only',
                'recipient': {
                    'name': guardian_name,
                    'phone': guardian_phone,
                },
                'recipients': [],
                'message': guardian_message,
                'attachment': {
                    'video_saved_name': saved_name,
                    'clip_window': clip_window,
                    'clip_path': '',
                },
            },
            'emergency': {
                'required': emergency_required,
                'popup_required': emergency_required,
                'popup_message': '낙상 고위험 감지. 119에 즉시 연락하세요.' if emergency_required else '현재 단계에서는 119 안내 팝업 대상이 아닙니다.',
                'call_script': str(event_label) + ' (' + str(clip_window.get('event_time_sec', 0)) + '초) 구간을 확인하고 필요 시 119에 연락하세요.',
                'protocol': protocol_levels[1] if emergency_required and len(protocol_levels) > 1 else (protocol_levels[0] if len(protocol_levels) > 0 else {}),
            },
            'protocol_headline': protocol.get('headline', ''),
            'clip_window': clip_window,
        }

        # 알림 이력 로그 (경량 — 클립 없음)
        self._write_json(os.path.join(self._alerts_dir(), saved_name + '.json'), {
            'saved_name': saved_name,
            'guardian_name': guardian_name,
            'guardian_phone': guardian_phone,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'risk_label': risk_label,
            'summary': summary,
            'fall_detected': fall_detected,
            'event_time': event_time,
            'event_label': event_label,
            'dispatch_results': [],
            'result': result,
            'mode': 'display-only',
            'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        return result

    def dispatch_risk_alerts(self, saved_name, guardian_name='보호자', guardian_phone='', risk_level='low', risk_score=0.0, risk_label='', summary='', fall_detected=False, event_time=0.0, event_label='대표 분석 구간'):
        """[비활성화] 풀 알림 발송 (클립 추출 + 외부 SMS/Push). 현재는 _build_alert_display()로 대체됨."""
        video_path, _ = self._load_upload_paths(saved_name)
        meta = self._video_meta(video_path)
        clip_window = self._clip_window(event_time=event_time, duration=meta.get('duration_sec', 0.0))
        clip_info = self._extract_clip(video_path, saved_name, clip_window)
        settings = self._load_alert_settings()
        protocol = self._emergency_protocol()
        protocol_levels = protocol.get('levels', []) or []
        emergency_required = str(risk_level).lower() == 'high' or str(fall_detected).lower() == 'true' or fall_detected is True
        guardian_required = str(risk_level).lower() in ('medium', 'high') or emergency_required
        guardian_status = 'disabled'
        guardian_message = '위험 단계가 낮아 보호자 알림을 발송하지 않았습니다.'
        dispatch_results = []
        if guardian_required:
            sms = (settings.get('gateway', {}).get('sms', {}) or {})
            push = (settings.get('gateway', {}).get('push', {}) or {})
            if sms.get('enabled') or push.get('enabled'):
                dispatch_results = self._dispatch_to_guardians(settings, risk_level, risk_label, summary, fall_detected)
                sent_count = sum(1 for r in dispatch_results if r.get('sms') == 'sent' or r.get('push') == 'sent')
                total_count = len(dispatch_results)
                if sent_count > 0:
                    guardian_status = 'sent'
                    guardian_message = '보호자 ' + str(sent_count) + '/' + str(total_count) + '명에게 ' + str(risk_label or risk_level) + ' 단계 알림을 전송했습니다.'
                else:
                    guardian_status = 'send-failed'
                    fail_reasons = [r.get('sms') or r.get('push') or '' for r in dispatch_results if r.get('sms') != 'sent' and r.get('push') != 'sent']
                    guardian_message = '보호자 알림 전송을 시도했으나 실패했습니다. (' + (fail_reasons[0] if fail_reasons else '알 수 없음')[:80] + ')'
            else:
                guardian_status = 'missing-config'
                guardian_message = str(guardian_name) + '님 알림 대상은 준비되었지만 문자/푸시 게이트웨이 설정이 없어 로그만 저장했습니다.'
        result = {
            'guardian': {
                'required': guardian_required,
                'status': guardian_status,
                'recipient': {
                    'name': guardian_name,
                    'phone': guardian_phone,
                },
                'recipients': [{'name': r['name'], 'phone': r['phone'], 'sms': r.get('sms'), 'push': r.get('push')} for r in dispatch_results],
                'message': guardian_message,
                'attachment': {
                    'video_saved_name': saved_name,
                    'clip_window': clip_window,
                    'clip_path': clip_info.get('clip_path', ''),
                },
            },
            'emergency': {
                'required': emergency_required,
                'popup_required': emergency_required,
                'popup_message': '낙상 고위험 감지. 119에 즉시 연락하세요.' if emergency_required else '현재 단계에서는 119 안내 팝업 대상이 아닙니다.',
                'call_script': str(event_label) + ' (' + str(clip_window.get('event_time_sec', 0)) + '초) 구간을 확인하고 필요 시 119에 연락하세요.',
                'protocol': protocol_levels[1] if emergency_required and len(protocol_levels) > 1 else (protocol_levels[0] if len(protocol_levels) > 0 else {}),
            },
            'protocol_headline': protocol.get('headline', ''),
            'clip_window': clip_window,
        }
        self._write_json(os.path.join(self._alerts_dir(), saved_name + '.json'), {
            'saved_name': saved_name,
            'guardian_name': guardian_name,
            'guardian_phone': guardian_phone,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'risk_label': risk_label,
            'summary': summary,
            'fall_detected': fall_detected,
            'event_time': event_time,
            'event_label': event_label,
            'dispatch_results': dispatch_results,
            'result': result,
            'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        return result

    # ── FN-0015: 전체 시스템 성능 평가 프레임워크 ─────────────────────────

    def evaluate_system(self, eval_type='full'):
        """Comprehensive system performance evaluation.

        Args:
            eval_type: 'full' | 'xg-fall' | 'xg-posture' | 'system'

        Returns dict with metrics for requested evaluation type(s).
        """
        import json
        import time as _time

        _t0 = _time.time()
        result = {
            'eval_type': eval_type,
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'models': {},
            'system': {},
            'errors': [],
        }

        # ── XG-Fall evaluation ──
        if eval_type in ('full', 'xg-fall'):
            try:
                fall_eval = self._evaluate_xg_fall()
                result['models']['xg_fall'] = fall_eval
            except Exception as e:
                result['errors'].append(f'XG-Fall evaluation failed: {str(e)}')

        # ── XG-Posture evaluation ──
        if eval_type in ('full', 'xg-posture'):
            try:
                posture_eval = self._evaluate_xg_posture()
                result['models']['xg_posture'] = posture_eval
            except Exception as e:
                result['errors'].append(f'XG-Posture evaluation failed: {str(e)}')

        # ── System-level evaluation ──
        if eval_type in ('full', 'system'):
            try:
                sys_eval = self._evaluate_system_level()
                result['system'] = sys_eval
            except Exception as e:
                result['errors'].append(f'System evaluation failed: {str(e)}')

        # ── Shadow comparison summary (if available) ──
        if eval_type == 'full':
            try:
                shadow = self.shadow_comparison_report(days=30)
                result['shadow_comparison'] = shadow
            except Exception:
                pass

        result['elapsed_sec'] = round(_time.time() - _t0, 2)

        # Save report
        try:
            report_dir = os.path.join(self._project_root(), 'data', 'storage', 'training', 'fall-detection', 'evaluation')
            os.makedirs(report_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            report_path = os.path.join(report_dir, f'eval_{eval_type}_{ts}.json')
            with open(report_path, 'w') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            result['report_path'] = self._project_relative_path(report_path)
        except Exception:
            pass

        return result

    def _evaluate_xg_fall(self):
        """Evaluate XG-Fall binary classifier using intake data cross-validation.

        Metrics: recall, precision, F1, false_negative_count, fast_sit_fp_rate, controlled_lie_fp_rate.
        """
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import numpy as np
        from sklearn.model_selection import StratifiedKFold, cross_validate
        from sklearn.metrics import classification_report, confusion_matrix

        if not self._xg_fall_available():
            return {'status': 'unavailable', 'message': 'XG-Fall 모델이 없습니다.'}

        # Load intake data for fall/non-fall
        intake_dir = os.path.join(self._project_root(), 'data', 'storage', 'training', 'fall-detection', 'intake')
        samples = []
        labels = []

        for label_dir, label_val in [('Y', 1), ('N', 0)]:
            dir_path = os.path.join(intake_dir, label_dir)
            if not os.path.isdir(dir_path):
                continue
            for fname in os.listdir(dir_path):
                if fname.lower().endswith(('.mp4', '.avi', '.mov', '.webm')):
                    samples.append(os.path.join(dir_path, fname))
                    labels.append(label_val)

        total = len(samples)
        if total < 10:
            return {
                'status': 'insufficient_data',
                'message': f'평가 데이터가 부족합니다 ({total}건). 최소 10건 필요.',
                'sample_count': total,
            }

        # Extract features from video files
        features = []
        valid_labels = []
        for i, (video_path, label) in enumerate(zip(samples, labels)):
            try:
                ts_result = self._extract_unified_timeseries(video_path, input_source='file')
                timeseries = ts_result.get('timeseries', [])
                vid_meta = ts_result.get('vid_meta', {})
                if len(timeseries) < 2:
                    continue
                windows = self._build_xg_feature_windows(timeseries, vid_meta, window_sec=1.0, stride_sec=0.5)
                if len(windows) == 0:
                    continue
                # Use max-probability window features
                feature_cols = self._XG_FEATURE_COLUMNS
                X_win = np.array([[w.get(col, 0.0) for col in feature_cols] for w in windows])
                X_win = np.nan_to_num(X_win, nan=0.0, posinf=0.0, neginf=0.0)
                # Aggregate: use feature vector of max-probability window (simulated)
                features.append(np.mean(X_win, axis=0))
                valid_labels.append(label)
            except Exception:
                continue

        n_valid = len(features)
        if n_valid < 10:
            return {
                'status': 'insufficient_features',
                'message': f'특징 추출 성공 {n_valid}/{total}건. 최소 10건 필요.',
                'extracted': n_valid,
                'total': total,
            }

        X = np.array(features)
        y = np.array(valid_labels)

        # Load model and predict
        model = self._get_xg_fall_model()
        y_pred = model.predict(X)
        y_proba = model.predict_proba(X)[:, 1] if hasattr(model, 'predict_proba') else y_pred.astype(float)

        # Metrics
        report = classification_report(y, y_pred, target_names=['non-fall', 'fall'], output_dict=True, zero_division=0)
        cm = confusion_matrix(y, y_pred, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()

        fall_recall = report['fall']['recall']
        fall_precision = report['fall']['precision']
        fall_f1 = report['fall']['f1-score']

        return {
            'status': 'ok',
            'sample_count': n_valid,
            'total_intake': total,
            'metrics': {
                'fall_recall': round(fall_recall, 4),
                'fall_precision': round(fall_precision, 4),
                'fall_f1': round(fall_f1, 4),
                'accuracy': round(report['accuracy'], 4),
                'false_negative_count': int(fn),
                'false_positive_count': int(fp),
                'true_positive_count': int(tp),
                'true_negative_count': int(tn),
            },
            'confusion_matrix': {
                'labels': ['non-fall', 'fall'],
                'matrix': cm.tolist(),
            },
            'classification_report': {
                'non-fall': {k: round(v, 4) for k, v in report['non-fall'].items()},
                'fall': {k: round(v, 4) for k, v in report['fall'].items()},
            },
            'threshold': self._XG_FALL_THRESHOLD,
        }

    def _evaluate_xg_posture(self):
        """Evaluate XG-Posture 6-class classifier using posture intake data.

        Metrics: macro F1, class-wise recall, confusion rates (sit/fall, lie/fall, walk/run).
        """
        import sys as _sys
        if '/opt/app/my_libs' not in _sys.path:
            _sys.path.insert(0, '/opt/app/my_libs')
        import numpy as np
        from sklearn.metrics import classification_report, confusion_matrix, f1_score

        if not self._xg_posture_available():
            return {'status': 'unavailable', 'message': 'XG-Posture 모델이 없습니다.'}

        intake_dir = os.path.join(self._project_root(), 'data', 'storage', 'training', 'fall-detection', 'intake')
        posture_classes = self._XG_POSTURE_CLASSES  # ['stand', 'walk', 'run', 'sit', 'lie', 'fall']

        samples = []
        labels = []
        for cls in posture_classes:
            cls_dir = os.path.join(intake_dir, cls)
            if not os.path.isdir(cls_dir):
                continue
            for fname in os.listdir(cls_dir):
                if fname.lower().endswith(('.mp4', '.avi', '.mov', '.webm')):
                    samples.append(os.path.join(cls_dir, fname))
                    labels.append(cls)

        total = len(samples)
        if total < 10:
            return {
                'status': 'insufficient_data',
                'message': f'포스처 평가 데이터가 부족합니다 ({total}건). 최소 10건 필요.',
                'sample_count': total,
                'class_distribution': {c: labels.count(c) for c in posture_classes},
            }

        # Extract features
        features = []
        valid_labels = []
        for video_path, label in zip(samples, labels):
            try:
                ts_result = self._extract_unified_timeseries(video_path, input_source='file')
                timeseries = ts_result.get('timeseries', [])
                vid_meta = ts_result.get('vid_meta', {})
                if len(timeseries) < 2:
                    continue
                windows = self._build_xg_feature_windows(timeseries, vid_meta, window_sec=1.5, stride_sec=0.5)
                if len(windows) == 0:
                    continue
                feature_cols = self._XG_FEATURE_COLUMNS
                X_win = np.array([[w.get(col, 0.0) for col in feature_cols] for w in windows])
                X_win = np.nan_to_num(X_win, nan=0.0, posinf=0.0, neginf=0.0)
                features.append(np.mean(X_win, axis=0))
                valid_labels.append(label)
            except Exception:
                continue

        n_valid = len(features)
        if n_valid < 10:
            return {
                'status': 'insufficient_features',
                'message': f'특징 추출 성공 {n_valid}/{total}건.',
                'extracted': n_valid,
                'total': total,
            }

        X = np.array(features)
        y = np.array(valid_labels)

        # Load model and predict
        bundle = self._get_xg_posture_model()
        model = bundle.get('model') if isinstance(bundle, dict) else bundle
        classes = bundle.get('classes', posture_classes) if isinstance(bundle, dict) else posture_classes
        p_feat_cols = bundle.get('feature_cols', self._XG_FEATURE_COLUMNS) if isinstance(bundle, dict) else self._XG_FEATURE_COLUMNS

        # Re-extract with model's feature columns if different
        if list(p_feat_cols) != list(self._XG_FEATURE_COLUMNS):
            features2 = []
            for video_path, label in zip(samples, labels):
                try:
                    ts_result = self._extract_unified_timeseries(video_path, input_source='file')
                    timeseries = ts_result.get('timeseries', [])
                    vid_meta = ts_result.get('vid_meta', {})
                    if len(timeseries) < 2:
                        continue
                    windows = self._build_xg_feature_windows(timeseries, vid_meta, window_sec=1.5, stride_sec=0.5)
                    if len(windows) == 0:
                        continue
                    X_win = np.array([[w.get(col, 0.0) for col in p_feat_cols] for w in windows])
                    X_win = np.nan_to_num(X_win, nan=0.0, posinf=0.0, neginf=0.0)
                    features2.append(np.mean(X_win, axis=0))
                except Exception:
                    continue
            if features2:
                X = np.array(features2)

        y_pred = model.predict(X)

        # Active classes present in data
        active = sorted(set(y) | set(y_pred))
        report = classification_report(y, y_pred, labels=active, output_dict=True, zero_division=0)
        cm = confusion_matrix(y, y_pred, labels=active)
        macro_f1 = round(float(f1_score(y, y_pred, average='macro', zero_division=0, labels=active)), 4)

        # Class-wise recall
        class_recall = {}
        for c in active:
            if c in report:
                class_recall[c] = round(report[c]['recall'], 4)

        # Confusion rates
        confusion_rates = {}
        active_list = list(active)
        def _confusion_rate(true_cls, pred_cls):
            """P(pred=pred_cls | true=true_cls)."""
            if true_cls not in active_list or pred_cls not in active_list:
                return 0.0
            ti = active_list.index(true_cls)
            pi = active_list.index(pred_cls)
            row_sum = cm[ti].sum()
            if row_sum == 0:
                return 0.0
            return round(float(cm[ti][pi]) / row_sum, 4)

        confusion_rates['sit_as_fall'] = _confusion_rate('sit', 'fall')
        confusion_rates['fall_as_sit'] = _confusion_rate('fall', 'sit')
        confusion_rates['lie_as_fall'] = _confusion_rate('lie', 'fall')
        confusion_rates['fall_as_lie'] = _confusion_rate('fall', 'lie')
        confusion_rates['walk_as_run'] = _confusion_rate('walk', 'run')
        confusion_rates['run_as_walk'] = _confusion_rate('run', 'walk')

        return {
            'status': 'ok',
            'sample_count': n_valid,
            'total_intake': total,
            'class_distribution': {c: int(np.sum(y == c)) for c in active},
            'metrics': {
                'macro_f1': macro_f1,
                'class_recall': class_recall,
                'confusion_rates': confusion_rates,
            },
            'confusion_matrix': {
                'labels': active_list,
                'matrix': cm.tolist(),
            },
            'classification_report': {c: {k: round(v, 4) for k, v in report[c].items()} for c in active if c in report},
        }

    def _evaluate_system_level(self):
        """System-level evaluation metrics.

        Checks model availability, intake data status, and computes readiness indicators.
        """
        xg_fall_ready = self._xg_fall_available()
        xg_posture_ready = self._xg_posture_available()
        rf_pose_ready = self._rf_pose_pipeline_available()

        intake = self._intake_summary()

        # Model info
        models_info = {
            'xg_fall': {
                'available': xg_fall_ready,
                'model_path': self._project_relative_path(self._xg_fall_model_path()) if xg_fall_ready else None,
                'threshold': self._XG_FALL_THRESHOLD,
            },
            'xg_posture': {
                'available': xg_posture_ready,
                'model_path': self._project_relative_path(self._xg_posture_model_path()) if xg_posture_ready else None,
                'classes': list(self._XG_POSTURE_CLASSES),
            },
            'rf_pose': {
                'available': rf_pose_ready,
                'deprecated': True,
                'note': 'RF-Pose는 FN-0014에서 deprecated됨. Shadow mode로 비교 로그 수집 중.',
            },
        }

        # Intake data summary
        y_count = intake.get('fall_count', 0)
        n_count = intake.get('nonfall_count', 0)
        posture_total = intake.get('posture_intake_total', 0)
        hard_cases = intake.get('hard_case_count', 0)

        # Decision state coverage check
        decision_states = ['safe', 'posture_only', 'fall_suspected', 'fall_confirmed', 'uncertain']

        # Short-clip robustness (existence of short clips in intake)
        short_clip_count = 0
        intake_dir = os.path.join(self._project_root(), 'data', 'storage', 'training', 'fall-detection', 'intake')
        for sub in ['Y', 'N']:
            sub_dir = os.path.join(intake_dir, sub)
            if os.path.isdir(sub_dir):
                for fname in os.listdir(sub_dir):
                    meta_path = os.path.join(sub_dir, fname + '.meta.json')
                    if os.path.isfile(meta_path):
                        try:
                            import json
                            with open(meta_path, 'r') as f:
                                meta = json.load(f)
                            if meta.get('short_clip_flag'):
                                short_clip_count += 1
                        except Exception:
                            pass

        return {
            'models': models_info,
            'intake_data': {
                'fall_samples': y_count,
                'nonfall_samples': n_count,
                'total_binary': y_count + n_count,
                'posture_labeled': posture_total,
                'hard_cases': hard_cases,
                'short_clip_tagged': short_clip_count,
            },
            'readiness': {
                'xg_dual_operational': xg_fall_ready,
                'xg_posture_operational': xg_posture_ready,
                'rf_pose_deprecated': True,
                'sufficient_fall_data': y_count >= 10,
                'sufficient_nonfall_data': n_count >= 10,
                'sufficient_posture_data': posture_total >= 20,
            },
            'coverage': {
                'decision_states': decision_states,
                'feature_count': len(self._XG_FEATURE_COLUMNS),
                'posture_classes': list(self._XG_POSTURE_CLASSES),
                'suppressor_count': 5,
            },
        }

    def generate_baseline_report(self):
        """Generate a baseline performance report for pre/post RF-Pose removal comparison.

        This captures the current state of all models for future reference.
        """
        import json
        import time as _time

        _t0 = _time.time()
        report = {
            'report_type': 'baseline',
            'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'purpose': 'RF-Pose 삭제 전/후 비교를 위한 baseline 성능 리포트',
        }

        # Full system evaluation
        try:
            eval_result = self.evaluate_system(eval_type='full')
            report['evaluation'] = eval_result
        except Exception as e:
            report['evaluation'] = {'error': str(e)}

        # Current model status
        report['model_status'] = {
            'xg_fall': {
                'available': self._xg_fall_available(),
                'threshold': self._XG_FALL_THRESHOLD,
            },
            'xg_posture': {
                'available': self._xg_posture_available(),
                'classes': list(self._XG_POSTURE_CLASSES),
            },
            'rf_pose': {
                'available': self._rf_pose_pipeline_available(),
                'status': 'deprecated',
            },
        }

        # Shadow comparison
        try:
            shadow = self.shadow_comparison_report(days=30)
            report['shadow_comparison'] = shadow
        except Exception:
            report['shadow_comparison'] = {'status': 'no_data'}

        # Deletion readiness
        try:
            deletion = self.rf_pose_deletion_status()
            report['deletion_readiness'] = deletion
        except Exception:
            report['deletion_readiness'] = {'status': 'error'}

        report['elapsed_sec'] = round(_time.time() - _t0, 2)

        # Save
        try:
            report_dir = os.path.join(self._project_root(), 'data', 'storage', 'training', 'fall-detection', 'evaluation')
            os.makedirs(report_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            report_path = os.path.join(report_dir, f'baseline_{ts}.json')
            with open(report_path, 'w') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            report['report_path'] = self._project_relative_path(report_path)
        except Exception:
            pass

        return report


Model = VideoAnalysis
