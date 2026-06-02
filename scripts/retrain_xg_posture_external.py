#!/usr/bin/env python3
import importlib.util
import json
import os
import sys


PROJECT_ROOT = '/opt/app/project/main'
MODULE_PATH = os.path.join(PROJECT_ROOT, 'src', 'model', 'struct', 'video_analysis.py')


class _Fs:
    def abspath(self):
        return PROJECT_ROOT


class _Project:
    def fs(self):
        return _Fs()


class _Wiz:
    project = _Project()


def main():
    spec = importlib.util.spec_from_file_location('project_video_analysis', MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load module: {MODULE_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.wiz = _Wiz()
    analyzer = module.VideoAnalysis(None)
    result = analyzer.retrain_xg_posture()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())