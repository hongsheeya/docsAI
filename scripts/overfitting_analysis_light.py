#!/usr/bin/env python3
"""FN-0027: Lightweight overfitting analysis - GroupKFold comparison
Uses smaller n_estimators for fast execution on limited CPU."""
import sys, json, numpy as np, pandas as pd
from sklearn.model_selection import StratifiedKFold, GroupKFold, cross_validate
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

sys.stdout.reconfigure(line_buffering=True)

feature_cols = ['center_dy','height_ratio','aspect_change','stillness','floor_proximity',
                'area_change','vert_horiz_ratio','max_down_speed','avg_conf','n_points']

df = pd.read_csv("storage/training/fall-detection/validation-features/features_combined.csv")
df['label'] = df['label'].replace({'Y': 1, 'N': 0}).astype(int)
df['prefix'] = df['video'].apply(lambda x: '_'.join(x.split('_')[:5]))
X = df[feature_cols].values
y = df['label'].values
groups = df['prefix'].values
print(f"Dataset: {len(df)} samples, {df['prefix'].nunique()} groups, Y={y.sum()}, N={len(y)-y.sum()}")

# Use lighter model for speed: n_estimators=50 instead of 200
pipeline = Pipeline([('scaler', StandardScaler()),
                     ('clf', XGBClassifier(n_estimators=50, max_depth=6, eval_metric='logloss', 
                                           random_state=42, n_jobs=1))])

print("\n[1/3] StratifiedKFold...")
cv1 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
res1 = cross_validate(pipeline, X, y, cv=cv1, scoring=['f1','roc_auc'], return_train_score=True, n_jobs=1)
print(f"  ValF1={res1['test_f1'].mean():.4f} TrainF1={res1['train_f1'].mean():.4f} Gap={res1['train_f1'].mean()-res1['test_f1'].mean():.4f} AUC={res1['test_roc_auc'].mean():.4f}")

print("\n[2/3] GroupKFold...")
cv2 = GroupKFold(n_splits=5)
res2 = cross_validate(pipeline, X, y, cv=cv2, scoring=['f1','roc_auc'], return_train_score=True, groups=groups, n_jobs=1)
print(f"  ValF1={res2['test_f1'].mean():.4f} TrainF1={res2['train_f1'].mean():.4f} Gap={res2['train_f1'].mean()-res2['test_f1'].mean():.4f} AUC={res2['test_roc_auc'].mean():.4f}")
print(f"  Folds={[round(v,4) for v in res2['test_f1']]}")

print("\n[3/3] Regularized+GroupKFold...")
pipeline_reg = Pipeline([('scaler', StandardScaler()),
    ('clf', XGBClassifier(n_estimators=50, max_depth=3, learning_rate=0.05, 
                          min_child_weight=10, reg_alpha=1.0, reg_lambda=5.0,
                          subsample=0.7, colsample_bytree=0.7,
                          eval_metric='logloss', random_state=42, n_jobs=1))])
res3 = cross_validate(pipeline_reg, X, y, cv=cv2, scoring=['f1','roc_auc'], return_train_score=True, groups=groups, n_jobs=1)
print(f"  ValF1={res3['test_f1'].mean():.4f} TrainF1={res3['train_f1'].mean():.4f} Gap={res3['train_f1'].mean()-res3['test_f1'].mean():.4f} AUC={res3['test_roc_auc'].mean():.4f}")
print(f"  Folds={[round(v,4) for v in res3['test_f1']]}")

# GroupKFold fold breakdown
print("\n=== GroupKFold fold breakdown ===")
for i, (train_idx, val_idx) in enumerate(cv2.split(X, y, groups)):
    yt, yv = y[train_idx], y[val_idx]
    ng = len(set(groups[val_idx]))
    print(f"  Fold{i+1}: train={len(yt)}(Y={yt.sum()},N={len(yt)-yt.sum()}) val={len(yv)}(Y={yv.sum()},N={len(yv)-yv.sum()}) groups={ng}")

print("\n=== SUMMARY ===")
print(f"{'Method':<30} {'ValF1':>7} {'TrainF1':>8} {'Gap':>7} {'AUC':>7}")
print(f"{'StratifiedKFold':<30} {res1['test_f1'].mean():>7.4f} {res1['train_f1'].mean():>8.4f} {res1['train_f1'].mean()-res1['test_f1'].mean():>7.4f} {res1['test_roc_auc'].mean():>7.4f}")
print(f"{'GroupKFold':<30} {res2['test_f1'].mean():>7.4f} {res2['train_f1'].mean():>8.4f} {res2['train_f1'].mean()-res2['test_f1'].mean():>7.4f} {res2['test_roc_auc'].mean():>7.4f}")
print(f"{'Regularized+GroupKFold':<30} {res3['test_f1'].mean():>7.4f} {res3['train_f1'].mean():>8.4f} {res3['train_f1'].mean()-res3['test_f1'].mean():>7.4f} {res3['test_roc_auc'].mean():>7.4f}")

results = {
    'stratified_kfold': {'val_f1': round(float(res1['test_f1'].mean()),4), 'train_f1': round(float(res1['train_f1'].mean()),4), 'gap': round(float(res1['train_f1'].mean()-res1['test_f1'].mean()),4), 'auc': round(float(res1['test_roc_auc'].mean()),4), 'per_fold_f1': [round(float(v),4) for v in res1['test_f1']]},
    'group_kfold': {'val_f1': round(float(res2['test_f1'].mean()),4), 'train_f1': round(float(res2['train_f1'].mean()),4), 'gap': round(float(res2['train_f1'].mean()-res2['test_f1'].mean()),4), 'auc': round(float(res2['test_roc_auc'].mean()),4), 'per_fold_f1': [round(float(v),4) for v in res2['test_f1']]},
    'regularized_group_kfold': {'val_f1': round(float(res3['test_f1'].mean()),4), 'train_f1': round(float(res3['train_f1'].mean()),4), 'gap': round(float(res3['train_f1'].mean()-res3['test_f1'].mean()),4), 'auc': round(float(res3['test_roc_auc'].mean()),4), 'per_fold_f1': [round(float(v),4) for v in res3['test_f1']]}
}
with open("storage/training/fall-detection/validation-features/overfitting_analysis.json", 'w') as f:
    json.dump(results, f, indent=2)
print("\nResults saved. DONE.")
