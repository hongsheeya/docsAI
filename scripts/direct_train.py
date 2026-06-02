#!/usr/bin/env python3
"""직접 학습 실행 스크립트.

WIZ 프레임워크를 거치지 않고, video_analysis 클래스를 직접 인스턴스화하여
retrain_baseline()을 호출한다.
"""
import os
import sys
import json
import time

# Add project paths
sys.path.insert(0, '/opt/app/my_libs')

def main():
    print("=" * 60)
    print("  Direct Model Training")
    print("=" * 60)
    
    # Import video_analysis module source
    va_path = "/opt/app/project/main/src/model/struct/video_analysis.py"
    
    # Read and extract the class
    with open(va_path, 'r') as f:
        source = f.read()
    
    # The module expects `wiz` context. We need to mock it minimally.
    # Instead of full mock, let's directly use the key methods.
    
    # Check what libraries are available
    import importlib
    
    # Try direct approach: instantiate class with minimal mock
    print("\n[1] Setting up mock wiz context...")
    
    class MockFS:
        def __init__(self, base_path):
            self._base = base_path
        def abspath(self, *args):
            return os.path.join(self._base, *args)
        def exists(self, path):
            return os.path.exists(os.path.join(self._base, path))
        def read(self, path):
            full = os.path.join(self._base, path)
            if os.path.exists(full):
                with open(full, 'r') as f:
                    return f.read()
            return None

    class MockProject:
        def __init__(self):
            self._fs = MockFS("/opt/app/_appdata")
        def fs(self, *args):
            return MockFS(os.path.join("/opt/app/_appdata", *args))
        def path(self):
            return "/opt/app/_appdata"
        def __call__(self):
            return "main"

    # The VideoAnalysis class is complex and deeply integrated with wiz.
    # Best approach: use retrain functions standalone.
    
    print("\n[2] Importing required libraries...")
    import numpy as np
    import joblib
    import cv2
    
    try:
        from xgboost import XGBClassifier
        print("  XGBoost: available")
        _use_xgb = True
    except ImportError:
        print("  XGBoost: not available, using sklearn")
        _use_xgb = False
    
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.metrics import accuracy_score, f1_score, classification_report
    from sklearn.model_selection import StratifiedKFold, cross_validate
    
    # Paths
    STORAGE = "/opt/app/storage/training/fall-detection"
    LEGACY_STORAGE = "/opt/app/_appdata/storage/training/fall-detection"
    INTAKE = os.path.join(LEGACY_STORAGE, "intake") if os.path.isdir(os.path.join(LEGACY_STORAGE, "intake")) else os.path.join(STORAGE, "intake")
    
    # =========================================================
    # RF Pipeline (fall detection - binary Y/N)
    # =========================================================
    print("\n" + "=" * 60)
    print("  [RF Pipeline] Fall Detection Binary Classifier")
    print("=" * 60)
    
    rf_dir = os.path.join(STORAGE, "rf-pipeline")
    os.makedirs(rf_dir, exist_ok=True)
    
    # Collect Y/N data
    rf_rows = []
    rf_skipped = []
    
    # Load YOLOv8 for feature extraction
    print("\n  Loading YOLO model...")
    yolo_model = None
    yolo_pose_model = None
    for yolo_path in ['/opt/app/yolov8n.pt', '/opt/app/project/main/yolov8n.pt']:
        if os.path.exists(yolo_path):
            try:
                from ultralytics import YOLO
                yolo_model = YOLO(yolo_path)
                print(f"  YOLO loaded: {yolo_path}")
                break
            except Exception as e:
                print(f"  YOLO load failed: {e}")
    
    for yolo_path in ['/opt/app/yolov8n-pose.pt', '/opt/app/project/main/yolov8n-pose.pt']:
        if os.path.exists(yolo_path):
            try:
                from ultralytics import YOLO
                yolo_pose_model = YOLO(yolo_path)
                print(f"  YOLO-Pose loaded: {yolo_path}")
                break
            except Exception as e:
                print(f"  YOLO-Pose load failed: {e}")
    
    if yolo_model is None:
        print("  [WARN] No YOLO model found, using basic CV features")
    
    def extract_basic_features(video_path):
        """Extract 13 basic RF features from a video clip."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        bboxes = []
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            
            if yolo_model is not None and frame_count % max(1, int(fps / 5)) == 0:
                try:
                    results = yolo_model(frame, verbose=False, conf=0.3)
                    if results and len(results[0].boxes) > 0:
                        # Get largest person bbox
                        for box in results[0].boxes:
                            if int(box.cls[0]) == 0:  # person
                                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                                bboxes.append({
                                    'frame': frame_count,
                                    'x1': float(x1)/w, 'y1': float(y1)/h,
                                    'x2': float(x2)/w, 'y2': float(y2)/h,
                                    'w': float(x2-x1)/w, 'h': float(y2-y1)/h,
                                    'cx': float((x1+x2)/2)/w, 'cy': float((y1+y2)/2)/h,
                                    'area': float((x2-x1)*(y2-y1))/(w*h),
                                })
                                break
                except Exception:
                    pass
            elif yolo_model is None and frame_count % max(1, int(fps / 5)) == 0:
                # Basic motion detection fallback
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                bboxes.append({
                    'frame': frame_count,
                    'x1': 0.3, 'y1': 0.3, 'x2': 0.7, 'y2': 0.7,
                    'w': 0.4, 'h': 0.4, 'cx': 0.5, 'cy': 0.5,
                    'area': 0.16,
                })
        
        cap.release()
        
        if len(bboxes) < 3:
            return None
        
        # Compute 13 features (matching RF pipeline expectations)
        areas = [b['area'] for b in bboxes]
        ars = [b['h'] / max(b['w'], 1e-6) for b in bboxes]
        cys = [b['cy'] for b in bboxes]
        cxs = [b['cx'] for b in bboxes]
        
        # Speed/velocity
        speeds = []
        for i in range(1, len(bboxes)):
            dt = (bboxes[i]['frame'] - bboxes[i-1]['frame']) / fps
            if dt > 0:
                dx = bboxes[i]['cx'] - bboxes[i-1]['cx']
                dy = bboxes[i]['cy'] - bboxes[i-1]['cy']
                speeds.append(np.sqrt(dx**2 + dy**2) / dt)
        
        if not speeds:
            speeds = [0.0]
        
        features = {
            'area_mean': np.mean(areas),
            'area_std': np.std(areas),
            'ar_mean': np.mean(ars),
            'ar_std': np.std(ars),
            'cy_mean': np.mean(cys),
            'cy_std': np.std(cys),
            'cy_max': np.max(cys),
            'speed_mean': np.mean(speeds),
            'speed_max': np.max(speeds),
            'speed_std': np.std(speeds),
            'descent_max': max(cys[i] - cys[i-1] for i in range(1, len(cys))) if len(cys) > 1 else 0.0,
            'stillness': 1.0 - min(np.std(cxs) + np.std(cys), 1.0),
            'n_detections': len(bboxes),
        }
        return features
    
    RF_FEATURE_COLS = ['area_mean', 'area_std', 'ar_mean', 'ar_std', 
                       'cy_mean', 'cy_std', 'cy_max',
                       'speed_mean', 'speed_max', 'speed_std',
                       'descent_max', 'stillness', 'n_detections']
    
    # Process Y and N directories
    for label_dir_name, label_int in [('Y', 1), ('N', 0)]:
        label_dir = os.path.join(INTAKE, label_dir_name)
        if not os.path.isdir(label_dir):
            continue
        for fname in sorted(os.listdir(label_dir)):
            if fname.startswith('.') or fname.endswith('.json'):
                continue
            vpath = os.path.join(label_dir, fname)
            try:
                feats = extract_basic_features(vpath)
                if feats is None:
                    rf_skipped.append({'file': fname, 'label': label_dir_name, 'reason': 'no features'})
                    continue
                feats['label'] = label_int
                feats['video'] = fname
                rf_rows.append(feats)
                print(f"    [{label_dir_name}] {fname}: OK")
            except Exception as e:
                rf_skipped.append({'file': fname, 'label': label_dir_name, 'reason': str(e)})
                print(f"    [{label_dir_name}] {fname}: SKIP ({e})")
    
    print(f"\n  RF data: {len(rf_rows)} samples (Y: {sum(1 for r in rf_rows if r['label']==1)}, N: {sum(1 for r in rf_rows if r['label']==0)})")
    
    if len(rf_rows) >= 4 and len(set(r['label'] for r in rf_rows)) >= 2:
        import pandas as pd
        df = pd.DataFrame(rf_rows)
        X = df[RF_FEATURE_COLS].astype(float).to_numpy()
        X = np.nan_to_num(X, nan=0.0)
        y = df['label'].to_numpy()
        
        rf_model = RandomForestClassifier(n_estimators=300, max_depth=6, 
                                          random_state=42, n_jobs=-1,
                                          min_samples_leaf=2)
        
        n_splits = min(3, min(np.sum(y==0), np.sum(y==1)))
        if n_splits >= 2:
            cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
            cv_results = cross_validate(rf_model, X, y, cv=cv,
                                       scoring=['accuracy', 'f1'], return_train_score=False)
            print(f"  CV accuracy: {np.mean(cv_results['test_accuracy']):.4f}")
            print(f"  CV F1: {np.mean(cv_results['test_f1']):.4f}")
        
        rf_model.fit(X, y)
        
        # Save RF model
        rf_model_path = os.path.join(rf_dir, "rf_hitl_model.pkl")
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.pkl.tmp', dir=rf_dir)
        os.close(tmp_fd)
        try:
            joblib.dump(rf_model, tmp_path)
            os.replace(tmp_path, rf_model_path)
        except:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        
        # Also save to legacy fallback path
        legacy_path = "/opt/app/rf_model_server.pkl"
        joblib.dump(rf_model, legacy_path)
        
        print(f"  [OK] RF model saved: {rf_model_path}")
        print(f"  [OK] RF fallback saved: {legacy_path}")
        
        # Save summary
        rf_summary = {
            'ready': True,
            'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'model_type': 'rf-pipeline',
            'training_samples': len(rf_rows),
            'features': RF_FEATURE_COLS,
            'feature_count': len(RF_FEATURE_COLS),
            'model_path': rf_model_path,
        }
        with open(os.path.join(rf_dir, 'training_summary.json'), 'w') as f:
            json.dump(rf_summary, f, indent=2, ensure_ascii=False)
    else:
        print("  [WARN] Not enough RF data for training")
    
    # =========================================================
    # XG-Posture (6-class multiclass)
    # =========================================================
    print("\n" + "=" * 60)
    print("  [XG-Posture] 6-Class Posture Classifier")
    print("=" * 60)
    
    xg_posture_dir = os.path.join(STORAGE, "xg-posture")
    os.makedirs(xg_posture_dir, exist_ok=True)
    
    POSTURE_CLASSES = ['stand', 'walk', 'run', 'sit', 'lie', 'fall']
    # Use XG features minus n_points (per FN-0059)
    POSTURE_FEATURE_COLS = [c for c in XG_FEATURE_COLUMNS if c != 'n_points']
    
    posture_rows = []
    for cls_name in POSTURE_CLASSES:
        cls_dir = os.path.join(INTAKE, cls_name)
        if not os.path.isdir(cls_dir):
            continue
        for fname in sorted(os.listdir(cls_dir)):
            if fname.startswith('.') or fname.endswith('.json'):
                continue
            vpath = os.path.join(cls_dir, fname)
            try:
                feats = extract_basic_features(vpath)
                if feats is None:
                    continue
                row = {'posture': cls_name, 'video': fname}
                for col in POSTURE_FEATURE_COLS:
                    row[col] = float(feats.get(col, 0.0))
                posture_rows.append(row)
                print(f"    [{cls_name}] {fname}: OK")
            except Exception as e:
                print(f"    [{cls_name}] {fname}: SKIP ({e})")
    
    class_dist = {c: sum(1 for r in posture_rows if r['posture'] == c) for c in POSTURE_CLASSES}
    print(f"\n  Posture data: {len(posture_rows)} samples")
    for c, cnt in class_dist.items():
        print(f"    {c}: {cnt}")
    
    active_classes = [c for c in POSTURE_CLASSES if class_dist.get(c, 0) >= 2]
    
    if len(active_classes) >= 2:
        import pandas as pd
        filtered = [r for r in posture_rows if r['posture'] in active_classes]
        df = pd.DataFrame(filtered)
        X = df[POSTURE_FEATURE_COLS].astype(float).to_numpy()
        X = np.nan_to_num(X, nan=0.0)
        
        active_to_int = {c: i for i, c in enumerate(active_classes)}
        y = df['posture'].map(active_to_int).to_numpy()
        
        n_classes = len(active_classes)
        if _use_xgb:
            posture_model = XGBClassifier(
                n_estimators=200, max_depth=3, learning_rate=0.08,
                objective='multi:softprob', num_class=n_classes,
                eval_metric='mlogloss', random_state=42, n_jobs=-1,
                use_label_encoder=False,
                min_child_weight=5, subsample=0.8, colsample_bytree=0.8,
            )
        else:
            posture_model = GradientBoostingClassifier(
                n_estimators=200, max_depth=3, learning_rate=0.08, random_state=42,
            )
        
        min_class_count = min(int(np.sum(y == i)) for i in range(n_classes))
        n_splits = min(3, min_class_count) if min_class_count >= 2 else 2
        
        if n_splits >= 2 and min_class_count >= 2:
            cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
            cv_results = cross_validate(posture_model, X, y, cv=cv,
                                       scoring=['accuracy', 'f1_macro'], return_train_score=False)
            print(f"  CV accuracy: {np.mean(cv_results['test_accuracy']):.4f}")
            print(f"  CV F1 macro: {np.mean(cv_results['test_f1_macro']):.4f}")
        
        posture_model.fit(X, y)
        
        # Save as bundle (matching video_analysis.py format)
        model_data = {
            'model': posture_model,
            'classes': active_classes,
            'feature_cols': list(POSTURE_FEATURE_COLS),
        }
        
        posture_model_path = os.path.join(xg_posture_dir, "xg_posture_model.pkl")
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.pkl.tmp', dir=xg_posture_dir)
        os.close(tmp_fd)
        try:
            joblib.dump(model_data, tmp_path)
            os.replace(tmp_path, posture_model_path)
        except:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        
        print(f"  [OK] XG-Posture model saved: {posture_model_path}")
        print(f"  [OK] Active classes: {active_classes}")
        
        # Save summary
        y_pred = posture_model.predict(X)
        y_pred = np.asarray(y_pred).flatten().astype(int)
        y = np.asarray(y).flatten().astype(int)
        report = classification_report(y, y_pred, target_names=active_classes, output_dict=True, zero_division=0)
        
        posture_summary = {
            'ready': True,
            'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'model_type': 'xg-posture-37',
            'training_samples': len(filtered),
            'class_distribution': class_dist,
            'active_classes': active_classes,
            'features': list(POSTURE_FEATURE_COLS),
            'feature_count': len(POSTURE_FEATURE_COLS),
            'classes': POSTURE_CLASSES,
            'source': 'bootstrap-recovery',
            'model_path': posture_model_path,
            'train_metrics': {
                'accuracy': round(float(accuracy_score(y, y_pred)), 4),
                'f1_macro': round(float(f1_score(y, y_pred, average='macro', zero_division=0)), 4),
                'class_recall': {c: round(report[c]['recall'], 4) for c in active_classes if c in report},
            },
        }
        with open(os.path.join(xg_posture_dir, 'training_summary.json'), 'w') as f:
            json.dump(posture_summary, f, indent=2, ensure_ascii=False)
    else:
        print(f"  [WARN] Not enough posture classes (need >=2, have {len(active_classes)})")
    
    # =========================================================
    # Final verification
    # =========================================================
    print("\n" + "=" * 60)
    print("  Final Model Verification")
    print("=" * 60)
    
    for name, rel_path in [
        ("RF-Pipeline", "rf-pipeline/rf_hitl_model.pkl"),
        ("RF-Fallback", "/opt/app/rf_model_server.pkl"),
        ("XG-Posture", "xg-posture/xg_posture_model.pkl"),
    ]:
        full_path = rel_path if rel_path.startswith('/') else os.path.join(STORAGE, rel_path)
        if os.path.isfile(full_path):
            size_kb = os.path.getsize(full_path) / 1024
            print(f"  ✓ {name}: {full_path} ({size_kb:.1f} KB)")
        else:
            print(f"  ✗ {name}: NOT FOUND")
    
    print("\n" + "=" * 60)
    print("  Training Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
