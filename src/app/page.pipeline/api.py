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


def prototype_info():
    data = video_analysis_model().prototype_info()
    wiz.response.status(200, **data)
