import json
import os


def video_analysis_model():
    struct = wiz.model("struct")
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
            wiz.response.status(400, message=str(e))
        wiz.response.status(200, **data)
    data = video_analysis.prototype_info()
    wiz.response.status(200, **data)


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
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


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
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


def retrain_baseline():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.retrain_baseline()
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


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
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


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
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


def reference_preview_info():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.reference_preview_info(wiz.request.query("scene_id", ""))
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


def reference_preview():
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.reference_preview_info(wiz.request.query("scene_id", ""))
    except Exception as e:
        wiz.response.status(400, message=str(e))
    clip_path = ((result.get('clip_info', {}) or {}).get('clip_path', ''))
    if len(clip_path) == 0 or not os.path.exists(clip_path):
        wiz.response.status(404, message='클립 파일을 찾을 수 없습니다.')
    wiz.response.download(clip_path, as_attachment=False)


def shadow_report():
    """FN-0014 Stage B: RF-Pose vs XG-Dual shadow comparison report."""
    video_analysis = video_analysis_model()
    days = int(wiz.request.query("days", 7))
    try:
        result = video_analysis.shadow_comparison_report(days=days)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


def rf_pose_deletion_status():
    """FN-0014 Stage C: RF-Pose deletion readiness check."""
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.rf_pose_deletion_status()
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


def evaluate_system():
    """FN-0015: System performance evaluation."""
    video_analysis = video_analysis_model()
    eval_type = wiz.request.query("eval_type", "full")
    try:
        result = video_analysis.evaluate_system(eval_type=eval_type)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


def baseline_report():
    """FN-0015: Generate baseline performance report."""
    video_analysis = video_analysis_model()
    try:
        result = video_analysis.generate_baseline_report()
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)
