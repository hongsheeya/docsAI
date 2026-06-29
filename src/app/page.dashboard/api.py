import importlib.util
import json
import math
import os
import sys


def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, 'item'):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, 'tolist'):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass
    return value


def _status(code=200, **payload):
    wiz.response.status(code, **_json_safe(payload))


def video_analysis_model():
    struct = wiz.model("struct")
    try:
        candidate_paths = []
        try:
            candidate_paths.append(wiz.project.fs().abspath('src', 'model', 'struct', 'video_analysis.py'))
        except Exception:
            try:
                candidate_paths.append(os.path.join(wiz.project.fs().abspath(), 'src', 'model', 'struct', 'video_analysis.py'))
            except Exception:
                pass
        candidate_paths.extend([
            '/mnt/data/wiz/project/main/bundle/src/model/struct/video_analysis.py',
            '/opt/app/project/main/bundle/src/model/struct/video_analysis.py',
            '/opt/app/project/main/build/src/model/struct/video_analysis.py',
            '/opt/app/project/main/src/model/struct/video_analysis.py',
        ])
        module_path = next((path for path in candidate_paths if os.path.isfile(path)), candidate_paths[0])
        module_name = f"project_video_analysis_{int(os.path.getmtime(module_path))}"
        if module_name in sys.modules:
            module = sys.modules[module_name]
            module.wiz = wiz
        else:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise Exception('video_analysis spec load failed')
            module = importlib.util.module_from_spec(spec)
            module.wiz = wiz
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        return module.VideoAnalysis(struct)
    except Exception:
        return struct.video_analysis


def prototype_info():
    video_analysis = video_analysis_model()
    action = wiz.request.query("action", "")
    if action == 'save_alert_settings':
        try:
            sms_timeout = int(wiz.request.query("sms_timeout_sec", "8") or 8)
            push_timeout = int(wiz.request.query("push_timeout_sec", "8") or 8)
            settings = {
                'guardian': {
                    'name': wiz.request.query("guardian_name", "보호자"),
                    'phone': wiz.request.query("guardian_phone", ""),
                },
                'gateway': {
                    'sms': {
                        'enabled': str(wiz.request.query("sms_enabled", "false")).lower() in ['1', 'true', 'yes', 'y'],
                        'provider_name': wiz.request.query("sms_provider_name", "solapi"),
                        'webhook_url': wiz.request.query("sms_webhook_url", ""),
                        'auth_token': wiz.request.query("sms_auth_token", ""),
                        'timeout_sec': sms_timeout,
                        'sender': wiz.request.query("sms_sender", ""),
                        'template_id': wiz.request.query("sms_template_id", ""),
                    },
                    'push': {
                        'enabled': str(wiz.request.query("push_enabled", "false")).lower() in ['1', 'true', 'yes', 'y'],
                        'provider_name': wiz.request.query("push_provider_name", "fcm"),
                        'webhook_url': wiz.request.query("push_webhook_url", ""),
                        'auth_token': wiz.request.query("push_auth_token", ""),
                        'timeout_sec': push_timeout,
                        'target': wiz.request.query("push_target", ""),
                        'platform': wiz.request.query("push_platform", "fcm"),
                        'bundle_id': wiz.request.query("push_bundle_id", ""),
                    }
                }
            }
            data = video_analysis.save_alert_settings(settings)
        except Exception as e:
            return _status(400, message=str(e))
        return _status(200, **data)
    try:
        data = video_analysis.prototype_info()
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **data)


def analyze_upload():
    video_analysis = video_analysis_model()
    metadata_raw = wiz.request.query("metadata", "{}")
    uploaded_file = wiz.request.file("video")
    try:
        metadata = json.loads(metadata_raw)
    except Exception:
        metadata = {}
    try:
        result = video_analysis.analyze_upload(uploaded_file, metadata)
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def warmup_models():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.warmup_models(model_type=wiz.request.query("model_type", "rf-dual"))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def model_registry():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.model_registry()
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def upload_model_asset():
    video_analysis = video_analysis_model()
    uploaded_file = wiz.request.file("model")
    family = wiz.request.query("family", "rf-fall-v2")
    label = wiz.request.query("label", "")
    note = wiz.request.query("note", "")
    metadata_raw = wiz.request.query("metadata", "{}")
    try:
        metadata = json.loads(metadata_raw)
    except Exception:
        metadata = {}
    try:
        result = video_analysis.upload_model_asset(uploaded_file, family=family, label=label, note=note, metadata=metadata)
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def delete_model_asset():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.delete_model_asset(wiz.request.query("model_id", ""))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def submit_training_sample():
    video_analysis = video_analysis_model()
    uploaded_file = wiz.request.file("video")
    label = wiz.request.query("label", "")
    note = wiz.request.query("note", "")
    metadata_raw = wiz.request.query("metadata", "{}")
    try:
        metadata = json.loads(metadata_raw)
    except Exception:
        metadata = {}
    try:
        result = video_analysis.submit_training_sample(uploaded_file, label, note, metadata)
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def retrain_baseline():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.retrain_baseline()
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def start_training_job():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.start_training_job(
            job_type=wiz.request.query("job_type", "full"),
            note=wiz.request.query("note", ""),
            apply_mode=wiz.request.query("apply_mode", "manual"),
            target_model=wiz.request.query("target_model", "rf-dual"),
            max_per_class=wiz.request.query("max_per_class", ""),
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def training_job_status():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.training_job_status(wiz.request.query("job_id", "latest"))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def continuous_training_status():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.continuous_training_status(wiz.request.query("name", "aihub82"))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def resume_continuous_training():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.resume_continuous_training(
            target=wiz.request.query("target", "all"),
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def apply_training_job():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.apply_training_job(wiz.request.query("job_id", "latest"))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def submit_analysis_feedback():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.submit_analysis_feedback(
            saved_name=wiz.request.query("saved_name", ""),
            predicted_label=wiz.request.query("predicted_label", ""),
            feedback_status=wiz.request.query("feedback_status", ""),
            actual_label=wiz.request.query("actual_label", ""),
            note=wiz.request.query("note", ""),
            retrain=str(wiz.request.query("retrain", "false")).lower() in ['1', 'true', 'yes', 'y'],
            posture_class=wiz.request.query("posture_class", ""),
            predicted_posture=wiz.request.query("predicted_posture", ""),
            ambiguity_flag=wiz.request.query("ambiguity_flag", "false"),
            occlusion_flag=wiz.request.query("occlusion_flag", "false"),
            short_clip_flag=wiz.request.query("short_clip_flag", "false"),
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def dispatch_risk_alerts():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis._build_alert_display(
            saved_name=wiz.request.query("saved_name", ""),
            risk_level=wiz.request.query("risk_level", "low"),
            risk_score=float(wiz.request.query("risk_score", "0") or 0),
            risk_label=wiz.request.query("risk_label", ""),
            summary=wiz.request.query("summary", ""),
            fall_detected=wiz.request.query("fall_detected", "false") == "true",
            event_time=float(wiz.request.query("event_time", "0") or 0),
            event_label=wiz.request.query("event_label", "대표 분석 구간"),
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def reference_preview_info():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.reference_preview_info(wiz.request.query("scene_id", ""))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def reference_preview():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.reference_preview_info(wiz.request.query("scene_id", ""))
    except Exception as e:
        return _status(400, message=str(e))
    clip_path = ((result.get('clip_info', {}) or {}).get('clip_path', ''))
    if len(clip_path) == 0 or not os.path.exists(clip_path):
        return _status(404, message='클립 파일을 찾을 수 없습니다.')
    wiz.response.download(clip_path, as_attachment=False)


def chunk_preview_info():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.chunk_preview_info(
            wiz.request.query("saved_name", ""),
            wiz.request.query("chunk_id", ""),
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def chunk_preview():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.chunk_preview_info(
            wiz.request.query("saved_name", ""),
            wiz.request.query("chunk_id", ""),
        )
    except Exception as e:
        return _status(400, message=str(e))
    clip_path = ((result.get('clip_info', {}) or {}).get('clip_path', ''))
    if len(clip_path) == 0 or not os.path.exists(clip_path):
        return _status(404, message='부분 영상 파일을 찾을 수 없습니다.')
    wiz.response.download(clip_path, as_attachment=False)


def analysis_video_info():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.upload_video_info(wiz.request.query("saved_name", ""))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def analysis_video():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.upload_video_info(wiz.request.query("saved_name", ""))
    except Exception as e:
        return _status(400, message=str(e))
    video_path = result.get('video_path', '')
    if len(video_path) == 0 or not os.path.exists(video_path):
        return _status(404, message='원본 영상 파일을 찾을 수 없습니다.')
    wiz.response.download(video_path, as_attachment=False)


def shadow_report():
    """FN-0014 Stage B: RF-Pose vs XG-Dual shadow comparison report."""
    video_analysis = video_analysis_model()
    days = int(wiz.request.query("days", 7))
    try:
        result = video_analysis.shadow_comparison_report(days=days)
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def rf_pose_deletion_status():
    """FN-0014 Stage C: RF-Pose deletion readiness check."""
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.rf_pose_deletion_status()
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def evaluate_system():
    """FN-0015: System performance evaluation."""
    video_analysis = video_analysis_model()
    eval_type = wiz.request.query("eval_type", "full")
    try:
        result = video_analysis.evaluate_system(eval_type=eval_type)
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def baseline_report():
    """FN-0015: Generate baseline performance report."""
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.generate_baseline_report()
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)
