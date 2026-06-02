#!/usr/bin/env python3
"""Train a lightweight driver-state auxiliary classifier from AI-Hub 173.

The first version uses the controlled-environment bbox subset because its
filenames contain stable state labels and its JSON annotations include face
boxes. The model is a candidate auxiliary signal for drowsiness/fatigue risk.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

try:
    _torch_threads = int(os.environ.get("TORCH_NUM_THREADS", "0") or 0)
    if _torch_threads > 0:
        torch.set_num_threads(_torch_threads)
except Exception:
    pass


CLASS_NAMES = ["normal_focus", "drowsy", "yawn", "phone_call", "smoking"]
CLASS_TO_KOR = {
    "normal_focus": "정상주시",
    "drowsy": "졸음재현",
    "yawn": "하품",
    "phone_call": "통화",
    "smoking": "흡연",
}
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def infer_label(filename: str) -> str | None:
    name = os.path.basename(filename)
    if "졸음재현" in name:
        return "drowsy"
    if "하품" in name:
        return "yawn"
    if "통화" in name:
        return "phone_call"
    if "흡연" in name:
        return "smoking"
    if "정상주시" in name:
        return "normal_focus"
    return None


def find_zip(root: Path, split: str, kind: str) -> Path:
    marker = "1.Training" if split == "train" else "2.Validation"
    area = "라벨링데이터" if kind == "label" else "원천데이터"
    for path in sorted(root.rglob("*.zip")):
        text = str(path)
        if marker in text and area in text and "bbox(통제환경)" in text:
            return path
    raise FileNotFoundError(f"missing {split}/{kind} bbox controlled zip under {root}")


def face_bbox(entry: dict) -> tuple[float, float, float, float] | None:
    box = (((entry or {}).get("ObjectInfo") or {}).get("BoundingBox") or {}).get("Face") or {}
    try:
        x = float(box.get("x"))
        y = float(box.get("y"))
        w = float(box.get("w"))
        h = float(box.get("h"))
        if w > 4 and h > 4:
            return x, y, x + w, y + h
    except Exception:
        return None
    return None


def load_label_meta(label_zip: Path, split: str) -> dict[str, dict]:
    meta = {}
    with zipfile.ZipFile(label_zip) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".json"):
                continue
            with zf.open(name) as fp:
                data = json.load(fp)
            file_name = ((data or {}).get("FileInfo") or {}).get("FileName") or os.path.basename(name).replace(".json", ".jpg")
            label = infer_label(file_name)
            if label not in CLASS_NAMES:
                continue
            meta[os.path.basename(file_name)] = {
                "label": label,
                "bbox": face_bbox(data),
                "split": split,
                "group": name.split("/", 1)[0],
            }
    return meta


def build_rows(root: Path, seed: int, max_train_per_class: int, max_val_per_class: int) -> list[dict]:
    rows_by_key = defaultdict(list)
    for split in ("train", "val"):
        label_zip = find_zip(root, split, "label")
        source_zip = find_zip(root, split, "source")
        labels = load_label_meta(label_zip, split)
        with zipfile.ZipFile(source_zip) as zf:
            for member in zf.namelist():
                if not member.lower().endswith(IMAGE_EXTS):
                    continue
                meta = labels.get(os.path.basename(member))
                if not meta:
                    label = infer_label(member)
                    if label not in CLASS_NAMES:
                        continue
                    meta = {"label": label, "bbox": None, "split": split, "group": member.split("/", 1)[0]}
                row = {
                    "zip_path": str(source_zip),
                    "member": member,
                    "label": meta["label"],
                    "split": split,
                    "bbox": meta.get("bbox"),
                    "group": meta.get("group") or member.split("/", 1)[0],
                }
                rows_by_key[(split, meta["label"])].append(row)
    rng = random.Random(seed)
    rows = []
    for split in ("train", "val"):
        cap = max_train_per_class if split == "train" else max_val_per_class
        for label in CLASS_NAMES:
            group = rows_by_key.get((split, label), [])
            rng.shuffle(group)
            rows.extend(group[:cap] if cap > 0 else group)
    return rows


class ZipImageDataset(Dataset):
    def __init__(self, rows: list[dict], class_to_idx: dict[str, int], image_size: int, train: bool):
        self.rows = rows
        self.class_to_idx = class_to_idx
        self._zip_cache = {}
        aug = [
            transforms.Resize((image_size, image_size)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.ColorJitter(brightness=0.18, contrast=0.18, saturation=0.12),
            transforms.RandomAffine(degrees=6, translate=(0.03, 0.03), scale=(0.94, 1.06)),
        ] if train else [transforms.Resize((image_size, image_size))]
        self.transform = transforms.Compose(aug + [
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

    def __len__(self):
        return len(self.rows)

    def _zip(self, path: str):
        zf = self._zip_cache.get(path)
        if zf is None:
            zf = zipfile.ZipFile(path)
            self._zip_cache[path] = zf
        return zf

    def __getitem__(self, idx: int):
        row = self.rows[idx]
        with self._zip(row["zip_path"]).open(row["member"]) as fp:
            img = Image.open(io.BytesIO(fp.read())).convert("RGB")
        bbox = row.get("bbox")
        if bbox:
            w, h = img.size
            x1, y1, x2, y2 = bbox
            pad_x = (x2 - x1) * 0.18
            pad_y = (y2 - y1) * 0.18
            x1 = max(0, int(x1 - pad_x))
            y1 = max(0, int(y1 - pad_y))
            x2 = min(w, int(x2 + pad_x))
            y2 = min(h, int(y2 + pad_y))
            if x2 > x1 and y2 > y1:
                img = img.crop((x1, y1, x2, y2))
        return self.transform(img), self.class_to_idx[row["label"]]


def make_model(num_classes: int, model_type: str = "mobilenet_v3_small"):
    model_type = str(model_type or "mobilenet_v3_small").strip().lower()
    try:
        if model_type == "mobilenet_v3_large":
            weights = models.MobileNet_V3_Large_Weights.DEFAULT
        else:
            weights = models.MobileNet_V3_Small_Weights.DEFAULT
    except Exception:
        weights = None
    if model_type == "mobilenet_v3_large":
        model = models.mobilenet_v3_large(weights=weights)
    else:
        model = models.mobilenet_v3_small(weights=weights)
    model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, num_classes)
    return model


def metrics_from_confusion(confusion: list[list[int]]) -> dict:
    total = sum(sum(row) for row in confusion)
    correct = sum(confusion[i][i] for i in range(len(confusion)))
    per_class = {}
    f1s = []
    for i, label in enumerate(CLASS_NAMES):
        tp = confusion[i][i]
        fp = sum(confusion[r][i] for r in range(len(confusion)) if r != i)
        fn = sum(confusion[i][c] for c in range(len(confusion)) if c != i)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = (2 * precision * recall) / max(precision + recall, 1e-9)
        per_class[label] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "support": sum(confusion[i])}
        f1s.append(f1)
    return {"accuracy": round(correct / max(total, 1), 4), "macro_f1": round(sum(f1s) / len(f1s), 4), "per_class": per_class, "confusion_matrix": confusion}


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    confusion = [[0 for _ in CLASS_NAMES] for _ in CLASS_NAMES]
    for x, y in loader:
        logits = model(x.to(device))
        pred = logits.argmax(dim=1).cpu().tolist()
        for truth, guess in zip(y.view(-1).tolist(), pred):
            confusion[int(truth)][int(guess)] += 1
    return metrics_from_confusion(confusion)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", default="/opt/app/datasets/facial_state/aihub_173_driver_state")
    parser.add_argument("--output-dir", default="/opt/app/storage/training/fall-detection/facial-state")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--image-size", type=int, default=160)
    parser.add_argument("--max-train-per-class", type=int, default=4000)
    parser.add_argument("--max-val-per-class", type=int, default=800)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-type", choices=["mobilenet_v3_small", "mobilenet_v3_large"], default="mobilenet_v3_small")
    parser.add_argument("--label-smoothing", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()

    rows = build_rows(Path(args.dataset_root), args.seed, args.max_train_per_class, args.max_val_per_class)
    counts = Counter((row["split"], row["label"]) for row in rows)
    print(f"[rows] total={len(rows)} class_counts={dict(counts)}", flush=True)
    if args.dry_run:
        return 0

    class_to_idx = {label: idx for idx, label in enumerate(CLASS_NAMES)}
    train_rows = [row for row in rows if row["split"] == "train"]
    val_rows = [row for row in rows if row["split"] == "val"]
    print(f"[split] train={len(train_rows)} val={len(val_rows)}", flush=True)

    train_loader = DataLoader(ZipImageDataset(train_rows, class_to_idx, args.image_size, True), batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers)
    val_loader = DataLoader(ZipImageDataset(val_rows, class_to_idx, args.image_size, False), batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = make_model(len(CLASS_NAMES), model_type=args.model_type).to(device)
    train_counts = Counter(row["label"] for row in train_rows)
    weights = torch.tensor([1.0 / max(train_counts.get(label, 1), 1) for label in CLASS_NAMES], dtype=torch.float32, device=device)
    weights = weights / weights.mean()
    try:
        criterion = nn.CrossEntropyLoss(weight=weights, label_smoothing=float(args.label_smoothing))
    except TypeError:
        criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    best = None
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        seen = 0
        loss_sum = 0.0
        for step, (x, y) in enumerate(train_loader, start=1):
            x = x.to(device)
            y = y.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()
            seen += int(y.numel())
            loss_sum += float(loss.item()) * int(y.numel())
            if step % max(1, round(1000 / max(args.batch_size, 1))) == 0 or step == len(train_loader):
                print(f"[train] epoch={epoch}/{args.epochs} step={step}/{len(train_loader)} loss={loss_sum / max(seen, 1):.4f}", flush=True)
        metrics = evaluate(model, val_loader, device)
        metrics["epoch"] = epoch
        metrics["train_loss"] = round(loss_sum / max(seen, 1), 4)
        history.append(metrics)
        print(f"[eval] epoch={epoch} acc={metrics['accuracy']:.4f} macro_f1={metrics['macro_f1']:.4f}", flush=True)
        if best is None or metrics["macro_f1"] > best["macro_f1"]:
            best = metrics
            torch.save({
                "model_type": args.model_type,
                "class_names": CLASS_NAMES,
                "class_to_korean": CLASS_TO_KOR,
                "image_size": args.image_size,
                "state_dict": model.state_dict(),
                "metrics": metrics,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }, out_dir / "aihub173_driver_state_mobilenetv3.pt")

    summary = {
        "ready": True,
        "dataset": "AI-Hub 173 driver state controlled bbox",
        "classes": CLASS_NAMES,
        "class_to_korean": CLASS_TO_KOR,
        "model_type": args.model_type,
        "label_smoothing": float(args.label_smoothing),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "best_metrics": best,
        "history": history,
        "output_model": str(out_dir / "aihub173_driver_state_mobilenetv3.pt"),
        "elapsed_sec": round(time.time() - start, 2),
    }
    with (out_dir / "aihub173_driver_state_summary.json").open("w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
