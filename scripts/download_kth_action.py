#!/usr/bin/env python3
"""KTH Action Recognition Dataset 다운로드 + 4초 클립 분할.

devlog/2026-04-06/020, 022 기록 기반 복원.
- walking.zip → intake/walk/ (최대 80 clips)
- running.zip → intake/run/ (최대 80 clips)
- jogging.zip → walk 폴더가 이미 80+ 이면 스킵, 아니면 walk에 추가
- 4초 클립, 1초 오버랩, 비디오당 최대 3클립
"""

import os
import sys
import glob
import shutil
import subprocess
import tempfile
import zipfile
import urllib.request

# KTH 공식 URL
KTH_BASE_URL = "https://www.csc.kth.se/cvap/actions"
ACTIONS = {
    "walking": "walk",
    "running": "run",
    "jogging": "walk",  # jogging → walk 매핑
}

CLIP_DURATION = 4   # 초
CLIP_OVERLAP = 1    # 초
MAX_CLIPS_PER_VIDEO = 3
MAX_CLIPS_PER_CLASS = 80

INTAKE_ROOT = None  # set in main()


def download_file(url, dest):
    """Download with progress."""
    print(f"  Downloading {url} ...")
    try:
        urllib.request.urlretrieve(url, dest)
        size_mb = os.path.getsize(dest) / (1024 * 1024)
        print(f"  Downloaded: {size_mb:.1f} MB")
        return True
    except Exception as e:
        print(f"  Download failed: {e}")
        # Fallback: try http
        if url.startswith("https://"):
            try:
                http_url = url.replace("https://", "http://")
                print(f"  Retrying with HTTP: {http_url}")
                urllib.request.urlretrieve(http_url, dest)
                size_mb = os.path.getsize(dest) / (1024 * 1024)
                print(f"  Downloaded: {size_mb:.1f} MB")
                return True
            except Exception as e2:
                print(f"  HTTP fallback also failed: {e2}")
        return False


def split_video_to_clips(video_path, output_dir, prefix, max_clips=MAX_CLIPS_PER_VIDEO):
    """Split a video into 4-second clips with 1s overlap using ffmpeg."""
    clips = []
    try:
        # Get duration
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30
        )
        duration = float(result.stdout.strip())
    except Exception:
        return clips

    stride = CLIP_DURATION - CLIP_OVERLAP  # 3 seconds
    start = 0
    clip_count = 0
    while start + CLIP_DURATION <= duration and clip_count < max_clips:
        out_name = f"{prefix}_clip{clip_count:02d}.mp4"
        out_path = os.path.join(output_dir, out_name)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(start), "-i", video_path,
                 "-t", str(CLIP_DURATION), "-c:v", "libx264", "-preset", "ultrafast",
                 "-an", "-loglevel", "error", out_path],
                timeout=60, check=True
            )
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                clips.append(out_path)
                clip_count += 1
        except Exception:
            pass
        start += stride

    return clips


def process_action(action_name, target_class):
    """Download one action zip and split into clips."""
    class_dir = os.path.join(INTAKE_ROOT, target_class)
    os.makedirs(class_dir, exist_ok=True)

    # Check existing count
    existing = len([f for f in os.listdir(class_dir) if f.endswith('.mp4')])
    if existing >= MAX_CLIPS_PER_CLASS:
        print(f"  {target_class}/ already has {existing} clips (>= {MAX_CLIPS_PER_CLASS}). Skipping {action_name}.")
        return existing

    zip_name = f"{action_name}.zip"
    zip_url = f"{KTH_BASE_URL}/{zip_name}"

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, zip_name)
        if not download_file(zip_url, zip_path):
            return existing

        # Extract
        print(f"  Extracting {zip_name} ...")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmpdir)
        except Exception as e:
            print(f"  Extract failed: {e}")
            return existing

        # Find AVI files (KTH format)
        avi_files = sorted(glob.glob(os.path.join(tmpdir, "**", "*.avi"), recursive=True))
        if not avi_files:
            # Try other formats
            avi_files = sorted(glob.glob(os.path.join(tmpdir, "**", "*.*"), recursive=True))
            avi_files = [f for f in avi_files if f.lower().endswith(('.avi', '.mp4', '.mov'))]

        print(f"  Found {len(avi_files)} source videos")

        total_clips = existing
        for avi in avi_files:
            if total_clips >= MAX_CLIPS_PER_CLASS:
                break
            basename = os.path.splitext(os.path.basename(avi))[0]
            remaining = MAX_CLIPS_PER_CLASS - total_clips
            max_c = min(MAX_CLIPS_PER_VIDEO, remaining)
            clips = split_video_to_clips(avi, class_dir, f"kth_{action_name}_{basename}", max_clips=max_c)
            total_clips += len(clips)

        print(f"  {target_class}/: {total_clips} clips total ({total_clips - existing} new)")
        return total_clips


def main():
    global INTAKE_ROOT

    # Determine project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # Use _appdata/storage path (what the training code expects)
    INTAKE_ROOT = os.path.join(project_root, "_appdata", "storage", "training",
                               "fall-detection", "intake")

    # Override: check if running from /opt/app context
    if os.path.exists("/opt/app/_appdata"):
        INTAKE_ROOT = "/opt/app/_appdata/storage/training/fall-detection/intake"

    print(f"Intake root: {INTAKE_ROOT}")

    # Create all class directories
    for cls in ["fall", "non-fall", "stand", "walk", "run", "sit", "lie", "hard-case"]:
        os.makedirs(os.path.join(INTAKE_ROOT, cls), exist_ok=True)

    # Also save original ZIPs for archival
    archive_dir = os.path.join(os.path.dirname(INTAKE_ROOT), "external-datasets", "kth")
    os.makedirs(archive_dir, exist_ok=True)

    print("\n=== KTH Action Recognition Dataset Download ===\n")

    for action, target in ACTIONS.items():
        print(f"\n[{action}] → {target}/")
        process_action(action, target)

    # Summary
    print("\n=== Summary ===")
    for cls in ["walk", "run", "stand", "sit", "lie", "fall"]:
        cls_dir = os.path.join(INTAKE_ROOT, cls)
        if os.path.isdir(cls_dir):
            count = len([f for f in os.listdir(cls_dir) if f.endswith('.mp4')])
            print(f"  {cls}: {count} clips")


if __name__ == "__main__":
    main()
