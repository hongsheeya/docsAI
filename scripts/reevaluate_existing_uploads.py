#!/usr/bin/env python3
import json
import os
import re
import subprocess
from pathlib import Path

UPLOAD_DIR = Path('/opt/app/_appdata/data/uploads/fall-detection-prototype')
OUT_PATH = Path('/opt/app/project/main/storage/training/fall-detection/evaluation/existing_uploads_reeval_20260414.json')
API_URL = 'http://localhost:3000/wiz/api/page.dashboard/analyze_upload'


def infer_label(name: str):
    upper = name.upper()
    if '_FY_' in upper or '_BY_' in upper or '_SY_' in upper:
        return 1
    if '_N_' in upper:
        return 0
    return None


def build_session():
    cmd = r'''
python3 -c "
from flask import Flask
app = Flask(__name__)
app.secret_key = 'season-wiz-secret'
with app.test_request_context():
    from flask import session as sess
    sess['id'] = 'admin'; sess['email'] = 'admin@test.com'; sess['role'] = 'admin'
    from flask.sessions import SecureCookieSessionInterface
    s = SecureCookieSessionInterface().get_signing_serializer(app)
    print(s.dumps(dict(sess)))
" 2>/dev/null
'''
    return subprocess.check_output(cmd, shell=True, text=True).strip()


def normalize_origin(name: str):
    m = re.search(r'((?:\d{5}|\d{8,})_[A-Z]_[A-Z]_(?:N|FY|BY|SY)_C\d\.mp4)$', name, re.I)
    if m:
        return m.group(1)
    return name


def main():
    session = build_session()
    files = sorted(UPLOAD_DIR.glob('*.mp4'))
    results = []
    for p in files:
        label = infer_label(p.name)
        out = Path('/tmp') / f'{p.name}.reeval.json'
        curl_cmd = [
            'curl', '-s', '-o', str(out),
            '-b', f'session={session}; season-wiz-project=main; season-wiz-devmode=true',
            '-F', f'video=@{p}',
            '-F', 'metadata={"model_type":"rf-dual"}',
            API_URL,
        ]
        subprocess.run(curl_cmd, check=True)
        with open(out, 'r', encoding='utf-8') as f:
            data = json.load(f).get('data', {})
        risk = data.get('risk_score')
        fall = data.get('fall_detected')
        pred = None if fall is None else (1 if fall else 0)
        item = {
            'file': p.name,
            'origin_name': normalize_origin(p.name),
            'true_label': label,
            'pred_label': pred,
            'fall_detected': fall,
            'risk_score': risk,
            'posture_label': data.get('posture_label'),
            'decision_state': data.get('decision_state'),
            'runtime_key': data.get('runtime_key'),
            'threshold': (data.get('risk_score_guide') or {}).get('threshold'),
            'runtime_warning': data.get('runtime_warning'),
        }
        results.append(item)

    fps = [r for r in results if r['true_label'] == 0 and r['pred_label'] == 1]
    fns = [r for r in results if r['true_label'] == 1 and r['pred_label'] == 0]
    summary = {
        'total_files': len(results),
        'labeled_files': len([r for r in results if r['true_label'] is not None]),
        'false_positives': len(fps),
        'false_negatives': len(fns),
        'results': results,
        'fp_list': fps,
        'fn_list': fns,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print('saved', OUT_PATH)
    print('total', len(results), 'fp', len(fps), 'fn', len(fns))


if __name__ == '__main__':
    main()
