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
        candidate_paths = [
            wiz.project.fs().abspath('src', 'model', 'struct', 'video_analysis.py'),
            '/opt/app/project/main/src/model/struct/video_analysis.py',
        ]
        module_path = next((path for path in candidate_paths if os.path.isfile(path)), candidate_paths[0])
        module_name = f"project_video_analysis_{int(os.path.getmtime(module_path))}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise Exception('video_analysis spec load failed')
        module = importlib.util.module_from_spec(spec)
        module.wiz = wiz
        spec.loader.exec_module(module)
        return module.VideoAnalysis(struct)
    except Exception:
        return struct.video_analysis


def model_registry():
    try:
        result = video_analysis_model().model_registry()
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def upload_model_asset():
    uploaded_file = wiz.request.file("model")
    metadata_raw = wiz.request.query("metadata", "{}")
    try:
        metadata = json.loads(metadata_raw)
    except Exception:
        metadata = {}
    try:
        result = video_analysis_model().upload_model_asset(
            uploaded_file,
            family=wiz.request.query("family", "rf-fall-v2"),
            label=wiz.request.query("label", ""),
            note=wiz.request.query("note", ""),
            metadata=metadata,
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def delete_model_asset():
    try:
        result = video_analysis_model().delete_model_asset(wiz.request.query("model_id", ""))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def cancel_model_delete():
    try:
        result = video_analysis_model().cancel_model_delete(wiz.request.query("model_id", ""))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def set_fall_sensitivity():
    try:
        result = video_analysis_model().set_fall_sensitivity(
            level=wiz.request.query("level", "50"),
            enabled=wiz.request.query("enabled", "true"),
            note=wiz.request.query("note", ""),
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def set_runtime_model_selection():
    try:
        result = video_analysis_model().set_runtime_model_selection(
            wiz.request.query("family", ""),
            wiz.request.query("model_id", ""),
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def save_runtime_model_bundle():
    selections_raw = wiz.request.query("selections", "{}")
    try:
        selections = json.loads(selections_raw)
    except Exception:
        selections = {}
    try:
        result = video_analysis_model().save_runtime_model_bundle(
            label=wiz.request.query("label", ""),
            selections=selections,
            description=wiz.request.query("description", ""),
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def apply_runtime_model_bundle():
    try:
        result = video_analysis_model().apply_runtime_model_bundle(wiz.request.query("bundle_id", ""))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def delete_runtime_model_bundle():
    try:
        result = video_analysis_model().delete_runtime_model_bundle(wiz.request.query("bundle_id", ""))
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)


def cleanup_model_candidates():
    try:
        result = video_analysis_model().cleanup_model_candidates(
            keep_per_family=wiz.request.query("keep_per_family", "2"),
            min_f1=wiz.request.query("min_f1", "0"),
        )
    except Exception as e:
        return _status(400, message=str(e))
    return _status(200, **result)
