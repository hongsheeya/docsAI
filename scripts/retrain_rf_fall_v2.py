#!/usr/bin/env python3
"""Train an occlusion-aware fall/non-fall RF model from AI-Hub fall videos.

This script writes a separate v2 model bundle and does not replace the legacy
RF pipeline. It samples videos by scenario group so camera views from the same
scenario do not leak across train/validation splits.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")
os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")

import cv2
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, VotingClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold, GroupShuffleSplit


PROJECT_ROOT = Path("/opt/app/project/main")
DATA_ROOTS = [
    Path("/opt/app/datasets/fall_classification/aihubs_71641/extracted_retry_20260511/영상"),
    Path("/opt/app/datasets/fall_classification/aihubs_71641/extracted/영상"),
    PROJECT_ROOT / "낙상영상" / "01.원천데이터" / "영상",
]
MODEL_DIR = Path("/opt/app/storage/training/fall-detection/rf-fall-v2")
PROJECT_MODEL_DIR = PROJECT_ROOT / "storage/training/fall-detection/rf-fall-v2"
MODEL_PATH = MODEL_DIR / "rf_fall_v2_model.pkl"
SUMMARY_PATH = MODEL_DIR / "training_summary.json"
ROWS_PATH = MODEL_DIR / "feature_rows.csv"
YOLO_PATH = PROJECT_ROOT / "yolov8n-pose.pt"

FEATURE_COLUMNS = [
    "detection_rate",
    "sample_coverage",
    "bbox_conf_mean",
    "bbox_conf_min",
    "center_y_mean",
    "center_y_std",
    "center_y_range",
    "center_y_start",
    "center_y_end",
    "center_y_drop",
    "center_y_drop_ratio",
    "center_y_slope",
    "max_down_speed_norm",
    "down_motion_ratio",
    "height_mean",
    "height_std",
    "height_start",
    "height_end",
    "height_drop_ratio",
    "height_min_ratio",
    "height_range_ratio",
    "width_mean",
    "width_std",
    "area_mean",
    "area_std",
    "area_start",
    "area_end",
    "area_drop_ratio",
    "area_range_ratio",
    "aspect_ratio_mean",
    "aspect_ratio_std",
    "aspect_start",
    "aspect_end",
    "aspect_rise",
    "aspect_max",
    "delta_y_mean",
    "delta_y_max",
    "delta_height_mean",
    "delta_width_mean",
    "delta_area_mean",
    "delta_y_accel_max",
    "final_height_ratio",
    "post_peak_stillness",
    "tail_stillness",
    "floor_proximity",
    "floor_contact_ratio",
    "low_height_floor_score",
    "avg_keypoint_conf",
    "visible_keypoint_ratio",
    "lower_body_visibility",
    "upper_body_visibility",
    "visibility_gap",
    "occlusion_ratio",
    "torso_tilt_mean",
    "torso_tilt_max",
    "torso_tilt_change",
    "pose_height_mean",
    "pose_height_min",
    "pose_width_mean",
    "horizontal_pose_score",
    "lying_skeleton_score",
    "standing_skeleton_score",
    "pose_height_drop",
    "fall_kinematic_score",
    "occlusion_fall_risk",
]


def safe_float(value: float, default: float = 0.0) -> float:
    try:
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except Exception:
        return default


def scenario_group(path: Path) -> str:
    stem = path.stem
    return re.sub(r"_C\d+$", "", stem)


def infer_label(path: Path) -> int | None:
    parts = set(path.parts)
    name = path.stem
    if "Y" in parts or re.search(r"_(FY|BY|SY)_", name):
        return 1
    if "N" in parts or re.search(r"_N_", name):
        return 0
    return None


try:
    cv2.setLogLevel(0)
except Exception:
    pass


def collect_videos(max_per_class: int, seed: int, min_file_mb: float, data_roots: list[Path]) -> list[dict]:
    videos = []
    seen = set()
    for root in data_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".mp4", ".avi", ".mov", ".mkv"}:
                continue
            real_key = (path.name, scenario_group(path), infer_label(path))
            if real_key in seen:
                continue
            try:
                if path.stat().st_size < min_file_mb * 1024 * 1024:
                    continue
            except OSError:
                continue
            label = infer_label(path)
            if label is None:
                continue
            seen.add(real_key)
            videos.append({"path": path, "label": label, "group": scenario_group(path)})

    rng = random.Random(seed)
    by_group = {}
    for item in videos:
        by_group.setdefault((item["label"], item["group"]), []).append(item)

    selected = []
    for label in (0, 1):
        groups = [g for (lbl, g) in by_group if lbl == label]
        rng.shuffle(groups)
        count = 0
        for group in groups:
            items = by_group[(label, group)][:]
            rng.shuffle(items)
            selected.extend(items[:2])
            count += len(items[:2])
            if max_per_class and count >= max_per_class:
                break
    rng.shuffle(selected)
    return selected


def sample_frames(video_path: Path, target_fps: float, max_frames: int, allow_seek_recovery: bool) -> tuple[list[tuple[int, float, np.ndarray]], dict]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return [], {"error": "open_failed"}
    fps = safe_float(cap.get(cv2.CAP_PROP_FPS), 30.0) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = total_frames / fps if fps > 0 and total_frames > 0 else 0.0
    if width <= 0 or height <= 0 or total_frames <= 0 or duration <= 0:
        cap.release()
        return [], {
            "error": "invalid_video_meta",
            "fps": fps,
            "total_frames": total_frames,
            "width": width,
            "height": height,
            "duration": duration,
            "sampled_frames": 0,
        }
    step = max(1, int(round(fps / max(target_fps, 0.1))))

    frames = []
    idx = 0
    failed_reads = 0
    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            failed_reads += 1
            if failed_reads >= 3:
                break
            break
        if idx % step == 0:
            t_sec = idx / fps if fps > 0 else 0.0
            frames.append((idx, t_sec, frame))
        idx += 1
    cap.release()

    if allow_seek_recovery and duration > 0 and len(frames) < min(max_frames, int(duration * target_fps * 0.5)):
        cap = cv2.VideoCapture(str(video_path))
        frames = []
        sample_count = min(max_frames, max(2, int(math.ceil(duration * target_fps))))
        for i in range(sample_count):
            t_sec = (duration * i / max(sample_count - 1, 1))
            frame_idx = int(round(t_sec * fps))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                frames.append((frame_idx, t_sec, frame))
        cap.release()

    meta = {
        "fps": fps,
        "total_frames": total_frames,
        "width": width,
        "height": height,
        "duration": duration,
        "sampled_frames": len(frames),
    }
    return frames, meta


def best_person_from_result(result):
    boxes = getattr(result, "boxes", None)
    keypoints = getattr(result, "keypoints", None)
    if boxes is None or len(boxes) == 0:
        return None
    xyxy = boxes.xyxy.cpu().numpy()
    conf = boxes.conf.cpu().numpy() if boxes.conf is not None else np.ones(len(xyxy))
    cls = boxes.cls.cpu().numpy() if boxes.cls is not None else np.zeros(len(xyxy))
    candidates = []
    for i, box in enumerate(xyxy):
        if int(cls[i]) != 0:
            continue
        x1, y1, x2, y2 = box
        area = max(0.0, (x2 - x1) * (y2 - y1))
        candidates.append((area * (0.5 + float(conf[i])), i))
    if not candidates:
        return None
    _, idx = max(candidates)
    kps = []
    if keypoints is not None and getattr(keypoints, "xy", None) is not None:
        xy = keypoints.xy.cpu().numpy()
        kp_conf = keypoints.conf.cpu().numpy() if getattr(keypoints, "conf", None) is not None else None
        if idx < len(xy):
            for j in range(min(17, xy.shape[1])):
                kps.append({
                    "x": safe_float(xy[idx, j, 0]),
                    "y": safe_float(xy[idx, j, 1]),
                    "conf": safe_float(kp_conf[idx, j] if kp_conf is not None else 1.0),
                })
    return {"xyxy": xyxy[idx].tolist(), "conf": safe_float(conf[idx]), "keypoints": kps}


def extract_timeseries(model, video_path: Path, target_fps: float, max_frames: int, imgsz: int, conf: float, allow_seek_recovery: bool) -> tuple[list[dict], dict]:
    frames, meta = sample_frames(video_path, target_fps=target_fps, max_frames=max_frames, allow_seek_recovery=allow_seek_recovery)
    if not frames:
        return [], meta
    width = max(int(meta.get("width") or 1), 1)
    height = max(int(meta.get("height") or 1), 1)
    timeseries = []
    for frame_idx, t_sec, frame in frames:
        try:
            results = model.predict(frame, imgsz=imgsz, conf=conf, verbose=False)
            person = best_person_from_result(results[0]) if results else None
        except Exception:
            person = None
        if not person:
            continue
        x1, y1, x2, y2 = person["xyxy"]
        x1 = max(0.0, min(float(x1), width))
        y1 = max(0.0, min(float(y1), height))
        x2 = max(0.0, min(float(x2), width))
        y2 = max(0.0, min(float(y2), height))
        bw = max(x2 - x1, 1.0)
        bh = max(y2 - y1, 1.0)
        keypoints = []
        for kp in person.get("keypoints", []):
            keypoints.append({
                "x": safe_float(kp.get("x")) / width,
                "y": safe_float(kp.get("y")) / height,
                "conf": safe_float(kp.get("conf")),
            })
        timeseries.append({
            "frame_idx": int(frame_idx),
            "time_sec": safe_float(t_sec),
            "bbox": {
                "cx": ((x1 + x2) * 0.5) / width,
                "cy": ((y1 + y2) * 0.5) / height,
                "w": bw / width,
                "h": bh / height,
                "conf": safe_float(person.get("conf")),
            },
            "keypoints": keypoints,
        })
    return timeseries, meta


def robust_slope(times: np.ndarray, values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    try:
        return safe_float(np.polyfit(times - times[0], values, 1)[0])
    except Exception:
        return 0.0


def compute_features(timeseries: list[dict], meta: dict) -> dict:
    sampled = max(int(meta.get("sampled_frames") or len(timeseries) or 1), 1)
    if not timeseries:
        return {col: 0.0 for col in FEATURE_COLUMNS}

    ordered = sorted(timeseries, key=lambda e: (safe_float(e.get("time_sec")), int(e.get("frame_idx") or 0)))
    t = np.array([safe_float(e.get("time_sec")) for e in ordered], dtype=float)
    b = [e["bbox"] for e in ordered]
    cx = np.array([safe_float(x.get("cx")) for x in b], dtype=float)
    cy = np.array([safe_float(x.get("cy")) for x in b], dtype=float)
    bw = np.array([safe_float(x.get("w")) for x in b], dtype=float)
    bh = np.array([safe_float(x.get("h")) for x in b], dtype=float)
    conf = np.array([safe_float(x.get("conf")) for x in b], dtype=float)
    area = bw * bh
    aspect = bw / (bh + 1e-6)
    dt = np.diff(t)
    dt = np.where(dt <= 1e-6, 1.0 / 6.0, dt)
    dcy = np.diff(cy, prepend=cy[0])
    down = np.clip(dcy, 0, None)
    speed_down = np.concatenate([[0.0], np.clip(np.diff(cy) / dt, 0, None)])
    accel_down = np.diff(speed_down, prepend=speed_down[0])
    tail_n = min(5, len(cy))
    head_n = min(5, len(cy))
    peak_idx = int(np.argmax(cy)) if len(cy) else 0
    post = cy[peak_idx:] if peak_idx < len(cy) else cy[-tail_n:]

    lower_idx = [11, 12, 13, 14, 15, 16]
    upper_idx = [0, 5, 6, 7, 8, 9, 10]
    torso_tilts = []
    pose_heights = []
    pose_widths = []
    avg_confs = []
    visible_ratios = []
    lower_vis = []
    upper_vis = []
    for entry in ordered:
        kps = entry.get("keypoints") or []
        if len(kps) < 17:
            avg_confs.append(0.0)
            visible_ratios.append(0.0)
            lower_vis.append(0.0)
            upper_vis.append(0.0)
            torso_tilts.append(0.0)
            pose_heights.append(0.0)
            pose_widths.append(0.0)
            continue
        kpc = np.array([safe_float(kp.get("conf")) for kp in kps[:17]], dtype=float)
        visible = kpc >= 0.25
        avg_confs.append(float(np.mean(kpc)))
        visible_ratios.append(float(np.mean(visible)))
        lower_vis.append(float(np.mean(visible[lower_idx])))
        upper_vis.append(float(np.mean(visible[upper_idx])))
        pts = np.array([[safe_float(kp.get("x")), safe_float(kp.get("y"))] for kp in kps[:17]], dtype=float)
        vis_pts = pts[visible]
        if len(vis_pts) >= 2:
            pose_heights.append(float(np.max(vis_pts[:, 1]) - np.min(vis_pts[:, 1])))
            pose_widths.append(float(np.max(vis_pts[:, 0]) - np.min(vis_pts[:, 0])))
        else:
            pose_heights.append(0.0)
            pose_widths.append(0.0)
        shoulders_ok = visible[5] and visible[6]
        hips_ok = visible[11] and visible[12]
        if shoulders_ok and hips_ok:
            shoulder_mid = (pts[5] + pts[6]) * 0.5
            hip_mid = (pts[11] + pts[12]) * 0.5
            vx, vy = hip_mid - shoulder_mid
            angle_from_vertical = abs(math.degrees(math.atan2(vx, vy if abs(vy) > 1e-6 else 1e-6)))
            torso_tilts.append(float(min(angle_from_vertical, 90.0)))
        else:
            torso_tilts.append(0.0)

    avg_conf = float(np.mean(avg_confs))
    visible_ratio = float(np.mean(visible_ratios))
    lower_body_visibility = float(np.mean(lower_vis))
    upper_body_visibility = float(np.mean(upper_vis))
    occlusion_ratio = 1.0 - visible_ratio
    pose_h = np.array(pose_heights, dtype=float)
    pose_w = np.array(pose_widths, dtype=float)
    torso = np.array(torso_tilts, dtype=float)

    floor_bottom = cy + (bh * 0.5)
    center_y_drop = float(np.mean(cy[-tail_n:]) - np.mean(cy[:head_n]))
    height_drop = float(np.mean(bh[:head_n]) - np.mean(bh[-tail_n:]))
    area_drop = float(np.mean(area[:head_n]) - np.mean(area[-tail_n:]))
    aspect_rise = float(np.mean(aspect[-tail_n:]) - np.mean(aspect[:head_n]))
    pose_height_drop = float(np.mean(pose_h[:head_n]) - np.mean(pose_h[-tail_n:])) if len(pose_h) else 0.0
    floor_contact_ratio = float(np.mean(floor_bottom >= 0.82))
    floor_proximity = float(np.mean(floor_bottom))
    horizontal_pose = float(np.mean(pose_w / (pose_h + 1e-6))) if len(pose_h) else 0.0
    lying_skeleton = float(np.mean((pose_w / (pose_h + 1e-6) >= 1.15) | (torso >= 45.0))) if len(pose_h) else 0.0
    standing_skeleton = float(np.mean((pose_h >= 0.22) & (torso <= 25.0))) if len(pose_h) else 0.0
    low_height_floor_score = float(max(0.0, min(1.0, (floor_proximity - 0.65) * 2.0 + max(0.0, 0.30 - np.mean(bh)) * 2.0)))
    kinematic = (
        max(0.0, center_y_drop) * 1.8
        + max(0.0, height_drop) * 1.4
        + max(0.0, area_drop) * 2.0
        + max(0.0, aspect_rise) * 0.8
        + float(np.max(speed_down) if len(speed_down) else 0.0) * 1.0
    )
    fall_kinematic_score = float(max(0.0, min(1.0, kinematic)))
    occlusion_fall_risk = float(max(0.0, min(1.0, occlusion_ratio * 0.45 + low_height_floor_score * 0.35 + fall_kinematic_score * 0.20)))

    feat = {
        "detection_rate": len(ordered) / sampled,
        "sample_coverage": len(ordered) / max(int(math.ceil((meta.get("duration") or 0) * 6.0)) or sampled, 1),
        "bbox_conf_mean": float(np.mean(conf)),
        "bbox_conf_min": float(np.min(conf)),
        "center_y_mean": float(np.mean(cy)),
        "center_y_std": float(np.std(cy)),
        "center_y_range": float(np.max(cy) - np.min(cy)),
        "center_y_start": float(np.mean(cy[:head_n])),
        "center_y_end": float(np.mean(cy[-tail_n:])),
        "center_y_drop": center_y_drop,
        "center_y_drop_ratio": center_y_drop / (float(np.mean(bh)) + 1e-6),
        "center_y_slope": robust_slope(t, cy),
        "max_down_speed_norm": float(np.max(speed_down) if len(speed_down) else 0.0),
        "down_motion_ratio": float(np.mean(dcy > 0.005)),
        "height_mean": float(np.mean(bh)),
        "height_std": float(np.std(bh)),
        "height_start": float(np.mean(bh[:head_n])),
        "height_end": float(np.mean(bh[-tail_n:])),
        "height_drop_ratio": height_drop / (float(np.mean(bh[:head_n])) + 1e-6),
        "height_min_ratio": float(np.min(bh) / (np.mean(bh) + 1e-6)),
        "height_range_ratio": float((np.max(bh) - np.min(bh)) / (np.mean(bh) + 1e-6)),
        "width_mean": float(np.mean(bw)),
        "width_std": float(np.std(bw)),
        "area_mean": float(np.mean(area)),
        "area_std": float(np.std(area)),
        "area_start": float(np.mean(area[:head_n])),
        "area_end": float(np.mean(area[-tail_n:])),
        "area_drop_ratio": area_drop / (float(np.mean(area[:head_n])) + 1e-6),
        "area_range_ratio": float((np.max(area) - np.min(area)) / (np.mean(area) + 1e-6)),
        "aspect_ratio_mean": float(np.mean(aspect)),
        "aspect_ratio_std": float(np.std(aspect)),
        "aspect_start": float(np.mean(aspect[:head_n])),
        "aspect_end": float(np.mean(aspect[-tail_n:])),
        "aspect_rise": aspect_rise,
        "aspect_max": float(np.max(aspect)),
        "delta_y_mean": float(np.mean(down)),
        "delta_y_max": float(np.max(down)),
        "delta_height_mean": float(np.mean(np.abs(np.diff(bh, prepend=bh[0])))),
        "delta_width_mean": float(np.mean(np.abs(np.diff(bw, prepend=bw[0])))),
        "delta_area_mean": float(np.mean(np.abs(np.diff(area, prepend=area[0])))),
        "delta_y_accel_max": float(np.max(np.clip(accel_down, 0, None)) if len(accel_down) else 0.0),
        "final_height_ratio": float(np.mean(bh[-tail_n:]) / (np.mean(bh) + 1e-6)),
        "post_peak_stillness": float(1.0 / (1.0 + np.std(post) * 20.0)) if len(post) else 0.0,
        "tail_stillness": float(1.0 / (1.0 + np.std(cy[-tail_n:]) * 20.0)),
        "floor_proximity": floor_proximity,
        "floor_contact_ratio": floor_contact_ratio,
        "low_height_floor_score": low_height_floor_score,
        "avg_keypoint_conf": avg_conf,
        "visible_keypoint_ratio": visible_ratio,
        "lower_body_visibility": lower_body_visibility,
        "upper_body_visibility": upper_body_visibility,
        "visibility_gap": upper_body_visibility - lower_body_visibility,
        "occlusion_ratio": occlusion_ratio,
        "torso_tilt_mean": float(np.mean(torso)) if len(torso) else 0.0,
        "torso_tilt_max": float(np.max(torso)) if len(torso) else 0.0,
        "torso_tilt_change": float(np.max(torso) - np.min(torso)) if len(torso) else 0.0,
        "pose_height_mean": float(np.mean(pose_h)) if len(pose_h) else 0.0,
        "pose_height_min": float(np.min(pose_h)) if len(pose_h) else 0.0,
        "pose_width_mean": float(np.mean(pose_w)) if len(pose_w) else 0.0,
        "horizontal_pose_score": horizontal_pose,
        "lying_skeleton_score": lying_skeleton,
        "standing_skeleton_score": standing_skeleton,
        "pose_height_drop": pose_height_drop,
        "fall_kinematic_score": fall_kinematic_score,
        "occlusion_fall_risk": occlusion_fall_risk,
    }
    return {col: safe_float(feat.get(col, 0.0)) for col in FEATURE_COLUMNS}


def threshold_search(y_true: np.ndarray, probs: np.ndarray) -> dict:
    best = {"threshold": 0.5, "f1": -1.0, "precision": 0.0, "recall": 0.0, "accuracy": 0.0}
    high_recall = None
    for threshold in np.linspace(0.15, 0.85, 141):
        pred = (probs >= threshold).astype(int)
        metrics = {
            "threshold": float(threshold),
            "accuracy": float(accuracy_score(y_true, pred)),
            "precision": float(precision_score(y_true, pred, zero_division=0)),
            "recall": float(recall_score(y_true, pred, zero_division=0)),
            "f1": float(f1_score(y_true, pred, zero_division=0)),
        }
        if metrics["f1"] > best["f1"]:
            best = metrics
        if metrics["recall"] >= 0.95:
            if high_recall is None or (metrics["precision"], metrics["f1"]) > (high_recall["precision"], high_recall["f1"]):
                high_recall = metrics
    if high_recall and high_recall["precision"] >= max(0.70, best["precision"] - 0.03):
        confirm = high_recall
    else:
        confirm = best
    suspect_candidates = []
    for threshold in np.linspace(0.05, confirm["threshold"], 81):
        pred = (probs >= threshold).astype(int)
        suspect_candidates.append({
            "threshold": float(threshold),
            "precision": float(precision_score(y_true, pred, zero_division=0)),
            "recall": float(recall_score(y_true, pred, zero_division=0)),
            "f1": float(f1_score(y_true, pred, zero_division=0)),
        })
    suspect = max(suspect_candidates, key=lambda m: (m["recall"] >= 0.98, m["f1"], m["precision"]))
    return {"best_f1": best, "confirm": confirm, "suspect": suspect}


def train(args: argparse.Namespace) -> dict:
    from ultralytics import YOLO

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    data_roots = [Path(p) for p in args.data_root] if args.data_root else DATA_ROOTS
    videos = collect_videos(args.max_per_class, args.seed, args.min_file_mb, data_roots)
    print(f"[collect] videos={len(videos)} labels={Counter(v['label'] for v in videos)}", flush=True)
    model = YOLO(str(YOLO_PATH))

    rows = []
    skipped = []
    started = time.time()
    for idx, item in enumerate(videos, 1):
        ts, meta = extract_timeseries(model, item["path"], args.target_fps, args.max_frames, args.imgsz, args.conf, args.seek_recovery)
        if len(ts) < args.min_detections:
            skipped.append({"path": str(item["path"]), "label": item["label"], "reason": "too_few_detections", "detections": len(ts)})
        else:
            feat = compute_features(ts, meta)
            feat.update({
                "label": int(item["label"]),
                "group": item["group"],
                "path": str(item["path"]),
                "detections": len(ts),
                "duration": safe_float(meta.get("duration")),
            })
            rows.append(feat)
        if idx % args.report_every == 0 or idx == len(videos):
            elapsed = time.time() - started
            rate = idx / elapsed if elapsed > 0 else 0.0
            eta = (len(videos) - idx) / rate if rate > 0 else 0.0
            print(f"[extract] {idx}/{len(videos)} rows={len(rows)} skipped={len(skipped)} elapsed={elapsed/60:.1f}m eta={eta/60:.1f}m", flush=True)

    if len(rows) < 20 or len(set(r["label"] for r in rows)) < 2:
        raise RuntimeError(f"Not enough rows to train: rows={len(rows)} labels={Counter(r['label'] for r in rows)}")

    df = pd.DataFrame(rows)
    df.to_csv(ROWS_PATH, index=False)
    X = df[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float)
    y = df["label"].to_numpy(dtype=int)
    groups = df["group"].astype(str).to_numpy()

    oof = np.zeros(len(y), dtype=float)
    splits = []
    unique_groups = len(set(groups))
    if unique_groups >= args.folds and min(Counter(y).values()) >= args.folds:
        cv = StratifiedGroupKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
        splits = list(cv.split(X, y, groups))
    else:
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=args.seed)
        splits = list(splitter.split(X, y, groups))

    fold_metrics = []
    for fold_idx, (tr, va) in enumerate(splits, 1):
        clf = VotingClassifier(
            estimators=[
                ("rf", RandomForestClassifier(
                    n_estimators=args.n_estimators,
                    max_depth=None,
                    min_samples_leaf=2,
                    class_weight="balanced_subsample",
                    random_state=args.seed + fold_idx,
                    n_jobs=args.n_jobs,
                )),
                ("et", ExtraTreesClassifier(
                    n_estimators=max(120, args.n_estimators // 2),
                    min_samples_leaf=2,
                    class_weight="balanced",
                    random_state=args.seed + 100 + fold_idx,
                    n_jobs=args.n_jobs,
                )),
            ],
            voting="soft",
            weights=[0.65, 0.35],
            n_jobs=args.n_jobs,
        )
        clf.fit(X[tr], y[tr])
        probs = clf.predict_proba(X[va])[:, list(clf.classes_).index(1)]
        oof[va] = probs
        fold_pred = (probs >= 0.5).astype(int)
        fold_metrics.append({
            "fold": fold_idx,
            "train": int(len(tr)),
            "validation": int(len(va)),
            "accuracy@0.5": float(accuracy_score(y[va], fold_pred)),
            "precision@0.5": float(precision_score(y[va], fold_pred, zero_division=0)),
            "recall@0.5": float(recall_score(y[va], fold_pred, zero_division=0)),
            "f1@0.5": float(f1_score(y[va], fold_pred, zero_division=0)),
        })
        print(f"[cv] fold={fold_idx} val={len(va)} f1@0.5={fold_metrics[-1]['f1@0.5']:.3f}", flush=True)

    thresholds = threshold_search(y, oof)
    confirm_t = thresholds["confirm"]["threshold"]
    final_pred = (oof >= confirm_t).astype(int)
    report = classification_report(y, final_pred, output_dict=True, zero_division=0)
    cm = confusion_matrix(y, final_pred, labels=[0, 1]).tolist()

    final = VotingClassifier(
        estimators=[
            ("rf", RandomForestClassifier(
                n_estimators=args.n_estimators,
                max_depth=None,
                min_samples_leaf=2,
                class_weight="balanced_subsample",
                random_state=args.seed,
                n_jobs=args.n_jobs,
            )),
            ("et", ExtraTreesClassifier(
                n_estimators=max(120, args.n_estimators // 2),
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=args.seed + 100,
                n_jobs=args.n_jobs,
            )),
        ],
        voting="soft",
        weights=[0.65, 0.35],
        n_jobs=args.n_jobs,
    )
    final.fit(X, y)

    importances = np.zeros(len(FEATURE_COLUMNS), dtype=float)
    fitted = final.named_estimators_
    for name, weight in [("rf", 0.65), ("et", 0.35)]:
        est = fitted.get(name)
        if est is not None and hasattr(est, "feature_importances_"):
            importances += np.array(est.feature_importances_) * weight
    top_features = [
        {"feature": FEATURE_COLUMNS[i], "importance": float(importances[i])}
        for i in np.argsort(importances)[::-1][:20]
    ]

    summary = {
        "model_type": "rf-fall-v2-occlusion-aware",
        "ready": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_roots": [str(p) for p in data_roots],
        "training_samples": int(len(y)),
        "class_distribution": {str(k): int(v) for k, v in Counter(y).items()},
        "group_count": int(len(set(groups))),
        "feature_count": len(FEATURE_COLUMNS),
        "features": FEATURE_COLUMNS,
        "target_fps": args.target_fps,
        "max_frames": args.max_frames,
        "thresholds": thresholds,
        "validation": {
            "accuracy": float(accuracy_score(y, final_pred)),
            "precision": float(precision_score(y, final_pred, zero_division=0)),
            "recall": float(recall_score(y, final_pred, zero_division=0)),
            "f1": float(f1_score(y, final_pred, zero_division=0)),
            "confusion_matrix_labels": [0, 1],
            "confusion_matrix": cm,
            "classification_report": report,
            "folds": fold_metrics,
        },
        "top_features": top_features,
        "skipped_count": len(skipped),
        "skipped_examples": skipped[:20],
        "notes": [
            "Scenario-group split prevents camera views of the same fall from leaking across validation.",
            "Features include upper/lower body visibility, torso tilt, floor contact, bbox collapse, and occlusion fall risk.",
        ],
    }

    bundle = {
        "model": final,
        "feature_cols": FEATURE_COLUMNS,
        "thresholds": {
            "confirm": float(thresholds["confirm"]["threshold"]),
            "suspect": float(thresholds["suspect"]["threshold"]),
        },
        "summary": summary,
        "created_at": summary["created_at"],
    }
    joblib.dump(bundle, MODEL_PATH)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    joblib.dump(bundle, PROJECT_MODEL_DIR / MODEL_PATH.name)
    (PROJECT_MODEL_DIR / SUMMARY_PATH.name).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    df.to_csv(PROJECT_MODEL_DIR / ROWS_PATH.name, index=False)
    print(f"[done] model={MODEL_PATH}", flush=True)
    print(f"[done] f1={summary['validation']['f1']:.3f} recall={summary['validation']['recall']:.3f} precision={summary['validation']['precision']:.3f} threshold={confirm_t:.3f}", flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-class", type=int, default=160)
    parser.add_argument("--target-fps", type=float, default=6.0)
    parser.add_argument("--max-frames", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.18)
    parser.add_argument("--min-file-mb", type=float, default=2.0)
    parser.add_argument("--seek-recovery", action="store_true")
    parser.add_argument("--min-detections", type=int, default=6)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--n-estimators", type=int, default=360)
    parser.add_argument("--n-jobs", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report-every", type=int, default=20)
    parser.add_argument("--data-root", action="append", default=[])
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
