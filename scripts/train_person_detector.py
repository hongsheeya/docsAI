#!/usr/bin/env python3
"""
FN-0015: Fine-tune YOLO11n person detector on pseudo-labeled dataset.
Freezes backbone, trains detection head only on indoor/hospital person data.

Usage:
    cd /opt/app/project/main
    python scripts/train_person_detector.py [--epochs 30] [--batch 8] [--imgsz 640]
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLO person detector on pseudo-labeled data"
    )
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--lr0", type=float, default=0.001)
    parser.add_argument("--freeze", type=int, default=10, help="Number of layers to freeze (backbone)")
    parser.add_argument(
        "--dataset",
        type=str,
        default="storage/training/fall-detection/person-detect/dataset/dataset.yaml",
    )
    parser.add_argument("--model", type=str, default="yolo11n.pt")
    parser.add_argument(
        "--output_dir",
        type=str,
        default="storage/training/fall-detection/person-detect/runs",
    )
    parser.add_argument("--name", type=str, default=None)
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Resolve paths
    dataset_yaml = (
        os.path.join(project_root, args.dataset)
        if not os.path.isabs(args.dataset)
        else args.dataset
    )
    model_path = (
        os.path.join(project_root, args.model)
        if not os.path.isabs(args.model)
        else args.model
    )
    output_dir = (
        os.path.join(project_root, args.output_dir)
        if not os.path.isabs(args.output_dir)
        else args.output_dir
    )

    run_name = args.name or f"person-det-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = os.path.join(output_dir, run_name)
    os.makedirs(run_dir, exist_ok=True)

    print(f"Dataset: {dataset_yaml}")
    print(f"Base model: {model_path}")
    print(f"Run dir: {run_dir}")
    print(f"Config: epochs={args.epochs}, batch={args.batch}, imgsz={args.imgsz}, "
          f"lr0={args.lr0}, freeze={args.freeze}")

    if not os.path.exists(dataset_yaml):
        print(f"ERROR: dataset.yaml not found at {dataset_yaml}")
        sys.exit(1)
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}")
        sys.exit(1)

    from ultralytics import YOLO

    # Load pretrained detection model
    model = YOLO(model_path)
    print(f"Loaded model: {len(model.names)} classes, task={model.task}")

    # Train with backbone freeze
    t0 = time.time()
    results = model.train(
        data=dataset_yaml,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        lr0=args.lr0,
        freeze=args.freeze,
        project=output_dir,
        name=run_name,
        exist_ok=True,
        # Augmentation
        mosaic=0.5,
        flipud=0.3,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.3,
        hsv_v=0.2,
        # CPU optimizations
        workers=2,
        device="cpu",
        # Save
        save=True,
        save_period=10,
        verbose=True,
        # Single class
        single_cls=True,
    )
    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"Training complete in {elapsed:.1f}s ({elapsed/60:.1f}min)")

    # Extract metrics
    best_weights = os.path.join(run_dir, "weights", "best.pt")
    last_weights = os.path.join(run_dir, "weights", "last.pt")

    metrics = {}
    try:
        # Load trained model and validate
        trained = YOLO(best_weights)
        val_results = trained.val(data=dataset_yaml, imgsz=args.imgsz, device="cpu")
        
        metrics = {
            "mAP50": round(float(val_results.box.map50), 4),
            "mAP50_95": round(float(val_results.box.map), 4),
            "precision": round(float(val_results.box.mp), 4),
            "recall": round(float(val_results.box.mr), 4),
        }
        print(f"Val metrics: {json.dumps(metrics, indent=2)}")
    except Exception as e:
        print(f"Warning: Could not extract val metrics: {e}")

    # Save training summary
    summary = {
        "run_name": run_name,
        "timestamp": datetime.now().isoformat(),
        "config": {
            "base_model": "yolo11n.pt",
            "epochs": args.epochs,
            "batch": args.batch,
            "imgsz": args.imgsz,
            "lr0": args.lr0,
            "freeze": args.freeze,
            "augmentation": {
                "mosaic": 0.5,
                "flipud": 0.3,
                "fliplr": 0.5,
                "hsv_h": 0.015,
            },
        },
        "metrics": metrics,
        "weights": {
            "best": best_weights if os.path.exists(best_weights) else None,
            "last": last_weights if os.path.exists(last_weights) else None,
        },
        "training_time_sec": round(elapsed, 2),
    }

    summary_path = os.path.join(run_dir, "training_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Update baseline_model.json with person detector path
    baseline_path = os.path.join(
        project_root, "storage/training/fall-detection/model/baseline_model.json"
    )
    try:
        if os.path.exists(baseline_path):
            with open(baseline_path, "r") as f:
                baseline = json.load(f)
        else:
            baseline = {}
        
        baseline["person_detector"] = {
            "weights": best_weights if os.path.exists(best_weights) else last_weights,
            "run_name": run_name,
            "metrics": metrics,
            "updated_at": datetime.now().isoformat(),
        }
        
        with open(baseline_path, "w") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)
        print(f"Updated baseline_model.json with person detector path")
    except Exception as e:
        print(f"Warning: Could not update baseline_model.json: {e}")

    print(f"\nSummary: {summary_path}")
    print(f"Best weights: {best_weights}")


if __name__ == "__main__":
    main()
