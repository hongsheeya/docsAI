import importlib.util
import os
import sys


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


def settings():
    video_analysis = video_analysis_model()
    try:
        data = video_analysis._public_llm_settings()
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **data)


def save_settings():
    video_analysis = video_analysis_model()
    try:
        settings = {
            'enabled': str(wiz.request.query("enabled", "false")).lower() in ['1', 'true', 'yes', 'y'],
            'provider': 'openai',
            'model': wiz.request.query("model", "gpt-4.1"),
            'api_key': wiz.request.query("api_key", ""),
            'api_key_action': wiz.request.query("api_key_action", ""),
            'temperature': wiz.request.query("temperature", "0.1"),
            'max_output_tokens': wiz.request.query("max_output_tokens", "700"),
            'mode': wiz.request.query("mode", "advisory"),
            'prompt_policy': wiz.request.query("prompt_policy", ""),
        }
        data = video_analysis.save_llm_settings(settings)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, **data)
