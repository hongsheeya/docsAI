import json


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


def alert_history():
    video_analysis = video_analysis_model()
    page = int(wiz.request.query("page", "1") or 1)
    page_size = int(wiz.request.query("page_size", "20") or 20)
    try:
        result = video_analysis.alert_history(page=page, page_size=page_size)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)


def save_guardians():
    video_analysis = video_analysis_model()
    guardians_raw = wiz.request.query("guardians", "[]")
    try:
        guardians = json.loads(guardians_raw)
    except Exception:
        guardians = []
    try:
        result = video_analysis.save_guardians(guardians)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **result)
