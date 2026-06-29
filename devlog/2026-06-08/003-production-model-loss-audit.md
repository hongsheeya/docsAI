# Production model loss audit

## What happened

- The real trained production artifacts for RF-Fall v2, AI-Hub 82 facial emotion, AI-Hub 173 driver state, and the XG-Posture occlusion auxiliary model were not found on the current server filesystem.
- The files visible after the emergency repair are not the original trained models:
  - `rf-fall-v2`: synthetic runtime-contract emergency artifact.
  - `xg-posture-occlusion-aux`: synthetic runtime-contract emergency artifact.
  - `aihub82` and `aihub173`: randomly initialized runtime-compatible checkpoints.
- These emergency artifacts are now marked `ready: false` and `operational_status: missing_real_model` so the runtime and dashboard do not treat them as recovered production models.

## Audit scope

- Checked persistent storage under `/mnt/data/wiz/storage` and `/mnt/data/wiz/models`.
- Checked project storage, git history, output directories, overlay backups, temporary directories, and container storage paths available on the server.
- Confirmed `git` does not track the trained model artifacts.
- Confirmed AI-Hub 82 dataset root has zero label/source zip files.
- Confirmed AI-Hub 173 training script cannot find the required controlled bbox label/source zip files.

## Root cause found

- The app had been storing operational models under `/opt/app/storage` and `/opt/app/models`.
- `/opt/app` is on the container overlay filesystem in this environment and is not durable across rebuild/reboot scenarios.
- The earlier persistent-storage note incorrectly treated `/opt/app/storage` as persistent here.

## Guard applied

- `/opt/app/storage` now points to `/mnt/data/wiz/storage`.
- `/opt/app/models` now points to `/mnt/data/wiz/models`.
- `/opt/app/run.sh` now recreates these symlinks at startup and copies any accidental overlay contents into the persistent locations before replacing them.

## Current state

- RF-Fall v2 real model: missing.
- AI-Hub 82 real trained checkpoint: missing; dataset root empty.
- AI-Hub 173 real trained checkpoint: missing; required dataset zips missing.
- XG-Posture occlusion auxiliary real model: missing.
- Existing XG-Posture bootstrap and legacy RF fallback artifacts remain present, but they are not a recovery of the missing four production models.

## Required recovery input

- Restore the real model backup archive or remount the original persistent volume that contains the trained artifacts.
- If retraining is required, restore/mount the AI-Hub 82 and AI-Hub 173 datasets first:
  - `/opt/app/datasets/facial_state/aihub_82_korean_emotion`
  - `/opt/app/datasets/facial_state/aihub_173_driver_state`
