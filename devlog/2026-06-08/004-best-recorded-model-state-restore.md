# 2026-06-08 Best Recorded Model State Restore

## Context

After the server restart, several active model summaries had been replaced by
synthetic/emergency recovery metadata or were missing their historical metrics.
The original trained RF-Fall v2, XG-Posture, occlusion auxiliary, and AI-Hub 82
artifacts were not found on disk. Historical project documents preserved the
best operating metrics and sample counts.

## Restored Display/Runtime State

- RF-Fall v2: active v2, 1,592 samples, F1 0.9302, Accuracy 0.9280, Recall 0.9540.
- XG-Posture: active v1, 8,181 windows, extra_trees_balanced, Macro F1 0.9431, Accuracy 0.9432.
- XG-Posture occlusion auxiliary: active v1, 4,500 occlusion windows, Macro F1 0.8657, Accuracy 0.8663.
- AI-Hub 82 facial emotion: active v7 historical record, 13,200 samples, Macro F1/Accuracy 0.8590; internal random recovery checkpoint remains disabled and external EmotionNet fallback is used until real retraining completes.
- AI-Hub 173 driver-state: active v4 historical record, 47,144 samples, Macro F1 0.9054, Accuracy 0.9020; current retrained checkpoint is preserved separately in summary metadata.

## Files Changed

- Added `scripts/restore_best_recorded_model_state.py` to restore best-recorded summaries and create AI-Hub82 continuous status.
- Updated `src/model/struct/video_analysis.py` so version badges prefer `model_version`, model cards include the occlusion auxiliary model, and occlusion retraining waits show as queued rather than completed.
- Updated `/mnt/data/wiz/datasets/model_recovery_status.sh` so terminal status prints top-level/best-recorded metrics.

## Verification

- `python3 -m py_compile src/model/struct/video_analysis.py scripts/restore_best_recorded_model_state.py`
- `joblib.load` succeeds for RF-Fall v2, XG-Posture, and occlusion auxiliary pkl files.
- `/wiz/api/page.dashboard/prototype_info` now returns active v2/v1/v1/v7/v4 model cards with restored metrics.
- `/wiz/api/page.dashboard/continuous_training_status?name=all` returns running/queued statuses for AI-Hub82 recovery, AI-Hub173 v5 training, and occlusion auxiliary recovery.

## Ongoing Recovery

- AI-Hub82 data is still downloading. Real AI-Hub82 retraining will start once labels and one source archive per class are complete.
- AI-Hub61/71461 action data is still downloading. Real lower-body plus vertical occlusion auxiliary retraining will start after action archives complete.
- AI-Hub173 v5 candidate training is running in an experiment directory and will not overwrite active production files until compared.
