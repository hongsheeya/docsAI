# AI-Hub redownload and retraining recovery

## Trigger

The real trained production artifacts for RF-Fall v2, AI-Hub 82 facial emotion,
AI-Hub 173 driver state, and XG-Posture occlusion auxiliary were confirmed
missing from the current server. Emergency/random-compatible artifacts remain
marked `ready: false` and must not be treated as production models.

## Persistent storage guard

- `/opt/app/datasets` now points to `/mnt/data/wiz/datasets`.
- `/opt/app/storage` now points to `/mnt/data/wiz/storage`.
- `/opt/app/models` now points to `/mnt/data/wiz/models`.
- `/opt/app/run.sh` recreates the dataset, storage, model, tools, and project
  output directories after reboot.
- `aihubshell` is also mirrored under `/mnt/data/wiz/tools/aihubshell`.

## Download queues

Primary queue:

- `/mnt/data/wiz/datasets/aihub_recovery_queue.sh`
- Status: `/opt/app/datasets/aihub_recovery_download_status.tsv`
- Logs: `/opt/app/datasets/logs/aihub_recovery/*.log`

Priority queue:

- `/mnt/data/wiz/datasets/aihub_priority_queue.sh`
- Downloads small labels and AI-Hub 173 validation source in parallel with the
  large AI-Hub 173 training source.

Progress command:

```bash
/mnt/data/wiz/datasets/aihub_recovery_status.sh
```

Combined training/download command:

```bash
/mnt/data/wiz/datasets/model_recovery_status.sh
```

## Recovery data plan

AI-Hub 173:

- Dataset key: `173`
- Controlled bbox train/validation labels and source.
- Expected compressed size: about 10 GB.
- Training script reads zip files directly, so no extraction is required.

AI-Hub 82:

- Dataset key: `82`
- First recovery subset: all 7 emotion label zips, one balanced training source
  shard per emotion, and all validation source zips.
- Expected compressed size: about 291 GB.
- Training script reads zip files directly, so no extraction is required.

AI-Hub 71641:

- Dataset key: `71641`
- File keys queued: labels, validation source, and all training split source
  parts.
- Expected compressed size: about 491 GB.
- Full extraction would exceed the persistent volume budget when combined with
  the compressed archives. RF retraining must use staged/streamed extraction or
  a zip-aware feature builder rather than blindly extracting everything.

## Training orchestration

Background orchestrator:

- `/mnt/data/wiz/datasets/model_recovery_orchestrator.sh`
- Status: `/opt/app/project/main/outputs/recovery_training_status/model_recovery_status.tsv`
- Logs: `/opt/app/project/main/outputs/recovery_training_status/`

Behavior:

- Polls for AI-Hub 173 zip readiness, then runs dry-run validation and CPU
  MobileNetV3 recovery training.
- Polls for AI-Hub 82 subset readiness, then runs dry-run validation and CPU
  MobileNetV3 seven-class recovery training.
- RF-Fall v2 retraining is intentionally blocked until the AI-Hub 71641 archive
  handling is made space-safe.

## Current model truth

- RF-Fall v2: real trained model missing.
- AI-Hub 82 facial emotion: real trained model missing.
- AI-Hub 173 driver state: real trained model missing.
- XG-Posture occlusion auxiliary: real trained model missing.
- XG-Posture base: still has an available ready artifact.
