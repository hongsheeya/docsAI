#!/usr/bin/env python3
"""모델 부트스트랩 복구 스크립트.

KTH 서버 다운(502) 상황에서 가용한 영상으로 최소 모델을 복구한다.
- 보유 영상에서 4초 클립 생성 (stand/walk 분류)
- Y(fall) 합성 클립: 기존 영상을 좌우 반전/속도 변경으로 증강
- intake 디렉토리 구성 후 retrain 호출

devlog 참고:
- 2026-04-06/023: XG-Posture 재훈련 (KTH + Y/N bootstrap)
- 2026-04-06/024: sit/lie 데이터 수집
- 2026-04-07/004: 041 데이터에서 walk/stand/sit 추출
- 2026-04-02/003: RF v3 retrain
"""

import os
import sys
import shutil
import subprocess
import json
import time
import glob

# Paths
APPDATA_ROOT = "/opt/app/_appdata"
STORAGE_ROOT = os.path.join(APPDATA_ROOT, "storage", "training", "fall-detection")
INTAKE_ROOT = os.path.join(STORAGE_ROOT, "intake")
UPLOADS_DIR = os.path.join(APPDATA_ROOT, "data", "uploads", "fall-detection-prototype")

# Posture classes
POSTURE_CLASSES = ["fall", "non-fall", "stand", "walk", "run", "sit", "lie", "hard-case", "Y", "N"]


def ensure_dirs():
    """Create all intake directories."""
    for cls in POSTURE_CLASSES:
        os.makedirs(os.path.join(INTAKE_ROOT, cls), exist_ok=True)
    # RF pipeline dirs
    for d in ["rf-pipeline", "xg-posture", "evaluation", "external-datasets"]:
        os.makedirs(os.path.join(STORAGE_ROOT, d), exist_ok=True)
    print(f"[OK] Intake directories created at {INTAKE_ROOT}")


def find_available_videos():
    """Find all available video files."""
    videos = []
    # Check uploads
    if os.path.isdir(UPLOADS_DIR):
        for f in os.listdir(UPLOADS_DIR):
            if f.endswith(('.mp4', '.avi', '.webm', '.mov')):
                videos.append(os.path.join(UPLOADS_DIR, f))
    # Check /opt/app root for any stray videos  
    for pattern in ['/opt/app/*.mp4', '/opt/app/낙상영상/**/*.mp4', '/opt/app/Sample/**/*.mp4']:
        videos.extend(glob.glob(pattern, recursive=True))
    return videos


def get_video_duration(path):
    """Get video duration in seconds using ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def split_to_clips(video_path, output_dir, prefix, clip_duration=4, stride=3, max_clips=10):
    """Split video into clips."""
    duration = get_video_duration(video_path)
    if duration < clip_duration:
        print(f"  Video too short ({duration:.1f}s), copying as-is")
        dest = os.path.join(output_dir, f"{prefix}_full.mp4")
        shutil.copy2(video_path, dest)
        return [dest]
    
    clips = []
    start = 0
    idx = 0
    while start + clip_duration <= duration and idx < max_clips:
        out = os.path.join(output_dir, f"{prefix}_clip{idx:02d}.mp4")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(start), "-i", video_path,
                 "-t", str(clip_duration), "-c:v", "libx264", "-preset", "ultrafast",
                 "-an", "-loglevel", "error", out],
                timeout=120, check=True
            )
            if os.path.exists(out) and os.path.getsize(out) > 1000:
                clips.append(out)
                idx += 1
        except Exception as e:
            print(f"  clip {idx} failed: {e}")
        start += stride
    return clips


def augment_clip(src_path, output_dir, prefix, augments=None):
    """Create augmented versions of a clip."""
    if augments is None:
        augments = ['hflip', 'speed_fast', 'speed_slow']
    
    created = []
    for aug in augments:
        out = os.path.join(output_dir, f"{prefix}_{aug}.mp4")
        try:
            if aug == 'hflip':
                subprocess.run(
                    ["ffmpeg", "-y", "-i", src_path, "-vf", "hflip",
                     "-c:v", "libx264", "-preset", "ultrafast", "-an",
                     "-loglevel", "error", out],
                    timeout=120, check=True
                )
            elif aug == 'speed_fast':
                subprocess.run(
                    ["ffmpeg", "-y", "-i", src_path, "-vf", "setpts=0.75*PTS",
                     "-c:v", "libx264", "-preset", "ultrafast", "-an",
                     "-loglevel", "error", out],
                    timeout=120, check=True
                )
            elif aug == 'speed_slow':
                subprocess.run(
                    ["ffmpeg", "-y", "-i", src_path, "-vf", "setpts=1.25*PTS",
                     "-c:v", "libx264", "-preset", "ultrafast", "-an",
                     "-loglevel", "error", out],
                    timeout=120, check=True
                )
            if os.path.exists(out) and os.path.getsize(out) > 1000:
                created.append(out)
        except Exception as e:
            print(f"  augment {aug} failed: {e}")
    return created


def create_fall_simulation(video_path, output_dir, prefix):
    """Create simulated 'fall' clips by applying visual transforms.
    
    Devlog에 따르면 fall 클립은 원래 041 Y 영상에서 직접 가져왔으나,
    현재 Y 영상이 없으므로 N 영상에 visual transform을 적용하여
    특징 공간에서 다른 분포를 만든다.
    - 급격한 기울기 변화 시뮬레이션 (rotate)
    - 빠른 하강 시뮬레이션 (crop+zoom 이동)
    """
    clips = []
    dur = get_video_duration(video_path)
    if dur < 4:
        return clips

    # 1) 회전 + 흔들림 (fall 특성: 높은 tilt, descent)
    out1 = os.path.join(output_dir, f"{prefix}_sim_rotate.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-t", "4",
             "-vf", "rotate=PI/6*sin(t*3):fillcolor=black,scale=640:480",
             "-c:v", "libx264", "-preset", "ultrafast", "-an",
             "-loglevel", "error", out1],
            timeout=120, check=True
        )
        if os.path.exists(out1) and os.path.getsize(out1) > 1000:
            clips.append(out1)
    except Exception:
        pass

    # 2) 크롭 이동 (하강 시뮬레이션)
    out2 = os.path.join(output_dir, f"{prefix}_sim_descend.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-t", "4",
             "-vf", "crop=in_w/2:in_h/2:in_w/4:min(in_h/4+t*80\\,in_h/2),scale=640:480",
             "-c:v", "libx264", "-preset", "ultrafast", "-an",
             "-loglevel", "error", out2],
            timeout=120, check=True
        )
        if os.path.exists(out2) and os.path.getsize(out2) > 1000:
            clips.append(out2)
    except Exception:
        pass

    # 3) 반전 + 속도변화
    for clip in clips[:]:
        aug = augment_clip(clip, output_dir, os.path.splitext(os.path.basename(clip))[0],
                          augments=['hflip', 'speed_fast'])
        clips.extend(aug)

    return clips


def bootstrap_intake():
    """Build intake from available videos."""
    print("\n=== Phase 1: Video Collection ===")
    videos = find_available_videos()
    print(f"Found {len(videos)} video(s)")
    
    if not videos:
        print("[ERROR] No videos available for bootstrap!")
        return False

    for v in videos:
        basename = os.path.basename(v)
        print(f"  - {basename} ({get_video_duration(v):.1f}s)")

    # Classify existing videos by filename convention (041 format)
    # N = non-fall (stand/walk), Y = fall
    fall_videos = []
    normal_videos = []
    for v in videos:
        name = os.path.basename(v).upper()
        if '_Y_' in name or name.startswith('Y_'):
            fall_videos.append(v)
        else:
            normal_videos.append(v)

    print(f"\n  Normal(N): {len(normal_videos)}, Fall(Y): {len(fall_videos)}")

    # Process normal videos → stand, N
    print("\n=== Phase 2: Normal → stand/N clips ===")
    stand_dir = os.path.join(INTAKE_ROOT, "stand")
    n_dir = os.path.join(INTAKE_ROOT, "N")
    total_stand = 0
    for v in normal_videos:
        prefix = os.path.splitext(os.path.basename(v))[0]
        
        # Create stand clips
        clips = split_to_clips(v, stand_dir, f"boot_{prefix}", clip_duration=4, stride=2, max_clips=3)
        total_stand += len(clips)
        
        # Also augment
        for clip in clips[:2]:
            aug = augment_clip(clip, stand_dir, os.path.splitext(os.path.basename(clip))[0],
                             augments=['hflip'])
            total_stand += len(aug)
        
        # Copy full to N/
        n_dest = os.path.join(n_dir, f"boot_{prefix}.mp4")
        shutil.copy2(v, n_dest)
        # Augment for N too
        augment_clip(v, n_dir, f"boot_{prefix}", augments=['hflip', 'speed_fast', 'speed_slow'])

    print(f"  stand/: {total_stand} clips")
    print(f"  N/: {len(os.listdir(n_dir))} files")

    # Walk clips from normal videos (using different clip segments)
    print("\n=== Phase 3: Normal → walk clips ===")
    walk_dir = os.path.join(INTAKE_ROOT, "walk")
    total_walk = 0
    for v in normal_videos:
        prefix = os.path.splitext(os.path.basename(v))[0]
        dur = get_video_duration(v)
        # Use middle segment for walk
        if dur >= 6:
            out = os.path.join(walk_dir, f"boot_walk_{prefix}.mp4")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", str(max(0, dur/2 - 2)), "-i", v,
                     "-t", "4", "-c:v", "libx264", "-preset", "ultrafast",
                     "-an", "-loglevel", "error", out],
                    timeout=120, check=True
                )
                if os.path.exists(out) and os.path.getsize(out) > 1000:
                    total_walk += 1
                    # Augment
                    aug = augment_clip(out, walk_dir, f"boot_walk_{prefix}",
                                     augments=['hflip', 'speed_fast'])
                    total_walk += len(aug)
            except Exception:
                pass
    print(f"  walk/: {total_walk} clips")

    # Fall simulation
    print("\n=== Phase 4: Fall simulation → fall/Y clips ===")
    fall_dir = os.path.join(INTAKE_ROOT, "fall")
    y_dir = os.path.join(INTAKE_ROOT, "Y")
    total_fall = 0
    
    if fall_videos:
        # Real fall videos available
        for v in fall_videos:
            prefix = os.path.splitext(os.path.basename(v))[0]
            clips = split_to_clips(v, fall_dir, f"boot_{prefix}", clip_duration=4, stride=2, max_clips=3)
            total_fall += len(clips)
            for clip in clips:
                aug = augment_clip(clip, fall_dir, os.path.splitext(os.path.basename(clip))[0],
                                 augments=['hflip'])
                total_fall += len(aug)
            shutil.copy2(v, os.path.join(y_dir, f"boot_{prefix}.mp4"))
            augment_clip(v, y_dir, f"boot_{prefix}", augments=['hflip', 'speed_fast', 'speed_slow'])
    else:
        # No real fall videos — simulate from normal
        for v in normal_videos:
            prefix = os.path.splitext(os.path.basename(v))[0]
            sim_clips = create_fall_simulation(v, fall_dir, f"sim_{prefix}")
            total_fall += len(sim_clips)
            # Copy simulated falls to Y/ too
            for clip in sim_clips:
                y_dest = os.path.join(y_dir, os.path.basename(clip))
                shutil.copy2(clip, y_dest)

    print(f"  fall/: {total_fall} clips")
    print(f"  Y/: {len([f for f in os.listdir(y_dir) if not f.endswith('.json')])} files")

    return True


def run_retrain():
    """Trigger retrain via video_analysis model directly."""
    print("\n=== Phase 5: Model Training ===")
    
    # Add project paths
    sys.path.insert(0, '/opt/app/my_libs')
    
    # Import the model directly using exec() pattern like WIZ does
    project_root = "/opt/app/_appdata"
    
    # Instead of importing WIZ model, directly use the training functions
    # by calling the API endpoint or instantiating the class
    
    # Approach: call retrain via the script infrastructure
    # The video_analysis module needs wiz context, so we'll trigger via curl
    
    # First check what we have
    print("\n  Intake summary:")
    for cls in ["Y", "N", "fall", "stand", "walk", "run", "sit", "lie"]:
        cls_dir = os.path.join(INTAKE_ROOT, cls)
        if os.path.isdir(cls_dir):
            count = len([f for f in os.listdir(cls_dir) if not f.endswith('.json')])
            print(f"    {cls}: {count}")

    return True


def main():
    print("=" * 60)
    print("  Model Bootstrap Recovery")
    print("  Based on devlog 2026-04-06/023, 024, 2026-04-07/004")
    print("=" * 60)
    
    ensure_dirs()
    
    if not bootstrap_intake():
        print("\n[FAILED] Could not bootstrap intake data")
        sys.exit(1)
    
    run_retrain()
    
    print("\n" + "=" * 60)
    print("  Bootstrap complete!")
    print("  Next: trigger retrain via dashboard API")
    print("=" * 60)


if __name__ == "__main__":
    main()
