#!/usr/bin/env python3
"""
FN-0017: Train fall classifiers (LR, RandomForest, XGBoost) on bbox trajectory features.

Input: fall_features_all.csv from FN-0016
Output: best_model.pkl + evaluation.json

Usage:
    cd /opt/app/project/main
    python scripts/train_fall_classifier.py
"""

import argparse
import csv
import json
import os
import pickle
import warnings

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    classification_report,
    confusion_matrix,
)

try:
    from xgboost import XGBClassifier

    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("WARNING: xgboost not installed, skipping XGBoost model")

warnings.filterwarnings("ignore")

FEATURE_COLS = [
    "center_dy",
    "height_ratio",
    "aspect_change",
    "stillness",
    "floor_proximity",
    "area_change",
    "vert_horiz_ratio",
    "max_down_speed",
    "avg_conf",
    "n_points",
]


def load_data(csv_path):
    """Load feature CSV and return X, y, video names."""
    with open(csv_path, "r") as f:
        rows = list(csv.DictReader(f))

    X = []
    y = []
    videos = []
    for r in rows:
        feats = [float(r[col]) for col in FEATURE_COLS]
        X.append(feats)
        y.append(1 if r["label"] == "Y" else 0)
        videos.append(r["video"])

    return np.array(X), np.array(y), videos


def get_models():
    """Return dict of model name -> Pipeline."""
    models = {
        "LogisticRegression": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(max_iter=1000, random_state=42)),
            ]
        ),
        "RandomForest": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    RandomForestClassifier(
                        n_estimators=100, random_state=42, n_jobs=-1
                    ),
                ),
            ]
        ),
    }
    if HAS_XGB:
        models["XGBoost"] = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    XGBClassifier(
                        max_depth=6,
                        n_estimators=200,
                        random_state=42,
                        eval_metric="logloss",
                        use_label_encoder=False,
                    ),
                ),
            ]
        )
    return models


def evaluate_models(X, y, models, n_splits=5):
    """Stratified K-Fold CV for each model. Returns results dict."""
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    results = {}

    for name, pipeline in models.items():
        print(f"\n  [{name}]")

        scoring = {
            "accuracy": "accuracy",
            "precision": "precision",
            "recall": "recall",
            "f1": "f1",
            "roc_auc": "roc_auc",
        }
        cv_results = cross_validate(
            pipeline, X, y, cv=skf, scoring=scoring, return_train_score=False
        )

        metrics = {}
        for metric_name in scoring:
            vals = cv_results[f"test_{metric_name}"]
            metrics[metric_name] = {
                "mean": round(float(np.mean(vals)), 4),
                "std": round(float(np.std(vals)), 4),
                "per_fold": [round(float(v), 4) for v in vals],
            }
            print(
                f"    {metric_name:12s}: {metrics[metric_name]['mean']:.4f} ± {metrics[metric_name]['std']:.4f}"
            )

        results[name] = metrics

    return results


def get_feature_importance(pipeline, feature_names):
    """Extract feature importance from fitted pipeline."""
    clf = pipeline.named_steps["clf"]
    importance = {}

    if hasattr(clf, "feature_importances_"):
        imp = clf.feature_importances_
        sorted_idx = np.argsort(imp)[::-1]
        for i, idx in enumerate(sorted_idx[:5]):
            importance[feature_names[idx]] = round(float(imp[idx]), 4)
    elif hasattr(clf, "coef_"):
        coef = np.abs(clf.coef_[0])
        sorted_idx = np.argsort(coef)[::-1]
        for i, idx in enumerate(sorted_idx[:5]):
            importance[feature_names[idx]] = round(float(coef[idx]), 4)

    return importance


def main():
    parser = argparse.ArgumentParser(description="Train fall classifiers")
    parser.add_argument(
        "--features_csv",
        type=str,
        default="storage/training/fall-detection/fall-features/fall_features_all.csv",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="storage/training/fall-detection/fall-classifier",
    )
    parser.add_argument("--cv_folds", type=int, default=5)
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    csv_path = (
        os.path.join(project_root, args.features_csv)
        if not os.path.isabs(args.features_csv)
        else args.features_csv
    )
    output_dir = (
        os.path.join(project_root, args.output_dir)
        if not os.path.isabs(args.output_dir)
        else args.output_dir
    )
    os.makedirs(output_dir, exist_ok=True)

    print(f"Features CSV: {csv_path}")
    print(f"Output dir: {output_dir}")

    # Load data
    X, y, videos = load_data(csv_path)
    print(f"\nDataset: {X.shape[0]} samples, {X.shape[1]} features")
    print(f"  Y (fall): {np.sum(y == 1)}, N (normal): {np.sum(y == 0)}")

    # Get models
    models = get_models()
    print(f"\nModels: {list(models.keys())}")

    # CV evaluation
    print(f"\n{'='*60}")
    print(f"Stratified {args.cv_folds}-Fold Cross Validation")
    print(f"{'='*60}")

    cv_results = evaluate_models(X, y, models, n_splits=args.cv_folds)

    # Find best model by F1
    best_name = max(cv_results, key=lambda k: cv_results[k]["f1"]["mean"])
    print(f"\n{'='*60}")
    print(f"Best model: {best_name} (F1={cv_results[best_name]['f1']['mean']:.4f})")

    # Train best model on full data
    best_pipeline = models[best_name]
    best_pipeline.fit(X, y)

    # Feature importance
    importance = get_feature_importance(best_pipeline, FEATURE_COLS)
    print(f"\nTop-5 Feature Importance ({best_name}):")
    for fname, score in importance.items():
        print(f"  {fname}: {score}")

    # Full data predictions (sanity check)
    y_pred = best_pipeline.predict(X)
    y_proba = best_pipeline.predict_proba(X)[:, 1]
    print(f"\nFull-data sanity check:")
    print(f"  Accuracy: {accuracy_score(y, y_pred):.4f}")
    print(f"  Precision: {precision_score(y, y_pred):.4f}")
    print(f"  Recall: {recall_score(y, y_pred):.4f}")
    print(f"  F1: {f1_score(y, y_pred):.4f}")
    print(f"  AUC-ROC: {roc_auc_score(y, y_proba):.4f}")

    cm = confusion_matrix(y, y_pred)
    print(f"\n  Confusion Matrix: TN={cm[0][0]} FP={cm[0][1]} FN={cm[1][0]} TP={cm[1][1]}")

    # Save model
    model_path = os.path.join(output_dir, "best_model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(best_pipeline, f)
    print(f"\nModel saved: {model_path}")

    # Also train and save all models
    all_importance = {}
    for name, pipeline in models.items():
        pipeline.fit(X, y)
        imp = get_feature_importance(pipeline, FEATURE_COLS)
        all_importance[name] = imp

        model_file = os.path.join(output_dir, f"{name.lower()}_model.pkl")
        with open(model_file, "wb") as f:
            pickle.dump(pipeline, f)

    # Save evaluation
    evaluation = {
        "best_model": best_name,
        "cv_folds": args.cv_folds,
        "dataset": {
            "total_samples": int(X.shape[0]),
            "features": int(X.shape[1]),
            "feature_names": FEATURE_COLS,
            "y_count": int(np.sum(y == 1)),
            "n_count": int(np.sum(y == 0)),
        },
        "cv_results": cv_results,
        "feature_importance": all_importance,
        "full_data_metrics": {
            "accuracy": round(float(accuracy_score(y, y_pred)), 4),
            "precision": round(float(precision_score(y, y_pred)), 4),
            "recall": round(float(recall_score(y, y_pred)), 4),
            "f1": round(float(f1_score(y, y_pred)), 4),
            "auc_roc": round(float(roc_auc_score(y, y_proba)), 4),
            "confusion_matrix": {
                "TN": int(cm[0][0]),
                "FP": int(cm[0][1]),
                "FN": int(cm[1][0]),
                "TP": int(cm[1][1]),
            },
        },
        "model_path": model_path,
    }

    eval_path = os.path.join(output_dir, "evaluation.json")
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=2)
    print(f"Evaluation saved: {eval_path}")

    print(f"\n{'='*60}")
    print("DONE")


if __name__ == "__main__":
    main()
