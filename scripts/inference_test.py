#!/usr/bin/env python3
"""FN-0029: Inference test on unseen validation videos."""
import sys, json, subprocess, time
sys.stdout.reconfigure(line_buffering=True)

PROJECT_ROOT = "/opt/app/project/main"
RUNTIME = f"{PROJECT_ROOT}/scripts/yolo_fall_runtime.py"

test_cases = [
    {
        "label": "Y (SY - 미끄러짐 낙상)",
        "video": "/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상/Y/SY/02673_H_A_SY_C3/02673_H_A_SY_C3.mp4",
        "expected": "fall"
    },
    {
        "label": "N (비낙상 일반)",
        "video": "/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상/N/N/00272_H_D_N_C8/00272_H_D_N_C8.mp4",
        "expected": "normal"
    }
]

results = []
for tc in test_cases:
    print(f"\n=== Testing: {tc['label']} ===")
    print(f"  Video: {tc['video'].split('/')[-1]}")
    start = time.time()
    try:
        cmd = [
            sys.executable, RUNTIME, "infer",
            "--project-root", PROJECT_ROOT,
            "--video", tc["video"],
            "--threshold", "0.5",
            "--mode", "person-feature",
            "--profile", "fast"
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        elapsed = time.time() - start
        
        # Parse JSON from output
        output = completed.stdout.strip()
        inference = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    inference = json.loads(line)
                    break
                except: pass
        
        if inference:
            score = float(inference.get('fall_score', 0.0))
            detected = bool(inference.get('fall_detected', False))
            windows = int(inference.get('windows', 0))
            tracks = int(inference.get('tracks', 0))
            top = inference.get('top_features', {})
            print(f"  fall_score: {score:.4f}")
            print(f"  fall_detected: {detected}")
            print(f"  tracks: {tracks}, windows: {windows}")
            print(f"  top_features: {json.dumps(top, indent=2)}")
            print(f"  elapsed: {elapsed:.1f}s")
            
            correct = (detected and tc['expected'] == 'fall') or (not detected and tc['expected'] == 'normal')
            print(f"  Expected: {tc['expected']}, Correct: {correct}")
            
            results.append({
                'test': tc['label'],
                'video': tc['video'].split('/')[-1],
                'fall_score': score,
                'fall_detected': detected,
                'expected': tc['expected'],
                'correct': correct,
                'elapsed_sec': round(elapsed, 1),
                'tracks': tracks,
                'windows': windows
            })
        else:
            print(f"  ERROR: Could not parse output")
            print(f"  stdout: {output[:500]}")
            print(f"  stderr: {completed.stderr[:500]}")
            results.append({'test': tc['label'], 'error': 'parse_failed', 'elapsed_sec': round(elapsed, 1)})
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT (>600s)")
        results.append({'test': tc['label'], 'error': 'timeout'})
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append({'test': tc['label'], 'error': str(e)})

print("\n=== SUMMARY ===")
for r in results:
    print(json.dumps(r, ensure_ascii=False))

with open(f"{PROJECT_ROOT}/storage/training/fall-detection/validation-features/inference_test.json", 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\nDONE")
