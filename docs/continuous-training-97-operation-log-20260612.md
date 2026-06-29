# FallAI Continuous Training Operation Log

Date: 2026-06-12 UTC

## Goal

Run dataset downloads and model retraining continuously in the background until every active model family reaches macro F1 97% or a clear data bottleneck is recorded.

## Current Priority

1. Keep AI-Hub 82 and AI-Hub 71461 downloads alive.
2. Let the active RF dashboard training finish; it is already running from uploaded RF-Fall data.
3. Keep AI-Hub 173 state training alive and promote only if the candidate is better than the active model.
4. Start/continue XG-Posture and occlusion auxiliary retraining when usable posture or AI-Hub pose JSON labels are ready.
5. If CPU pressure gets high, lower priority for heavy RF/posture jobs before interrupting any download.

## Runtime Controls

- All-model supervisor target: `0.97`
- Target ladder: `0.90, 0.93, 0.95, 0.97`
- Supervisor status: `/mnt/data/wiz/storage/training/fall-detection/continuous-model-supervisor/status.json`
- Feature/version audit: `/mnt/data/wiz/storage/training/fall-detection/continuous-model-supervisor/model_feature_version_audit.jsonl`
- Latest feature snapshot: `/mnt/data/wiz/storage/training/fall-detection/continuous-model-supervisor/latest_model_feature_snapshot.json`
- AI-Hub 82 status: `/mnt/data/wiz/storage/project-main/outputs/continuous_training/aihub82_status.json`
- AI-Hub 173 status: `/mnt/data/wiz/storage/project-main/outputs/continuous_training/aihub173_status.json`
- XG-Posture status: `/mnt/data/wiz/storage/project-main/outputs/continuous_training/xg-posture_status.json`

## CPU Allocation

- RF dashboard training is allowed to continue but should run at lower priority when it dominates CPU.
- AI-Hub 173 training is kept lower than downloads and interactive server work.
- Downloads should not be killed just because model training is active.

## Occlusion Sweep

Occlusion auxiliary retraining uses synthetic lower-body and side occlusion augmentation:

- Lower-body modes: `waist`, `thigh`, `knee`, `random_mild`, `random_moderate`, `random_severe`
- Side/vertical modes: `left`, `right`, `left_mild`, `left_moderate`, `left_severe`, `right_mild`, `right_moderate`, `right_severe`

Trigger policy candidates:

| avg_conf_lt | lower_body_visibility_lt | posture_margin_lt |
| ---: | ---: | ---: |
| 0.30 | 0.36 | 0.05 |
| 0.34 | 0.38 | 0.05 |
| 0.36 | 0.40 | 0.06 |
| 0.38 | 0.42 | 0.07 |
| 0.40 | 0.44 | 0.08 |
| 0.42 | 0.46 | 0.07 |
| 0.44 | 0.48 | 0.08 |
| 0.46 | 0.50 | 0.09 |
| 0.50 | 0.52 | 0.10 |
| 0.52 | 0.56 | 0.11 |

Selection rule: apply the best candidate only when holdout performance improves without hurting fall recall; otherwise keep the current active model and record the bottleneck.

## Notes

- The `0.38` value is not a literal "38% of the body is hidden" rule. It is a low-confidence/lower-body-visibility trigger threshold used with the auxiliary posture model.
- Active production models must stay protected from deletion. Candidate cleanup should use a grace period instead of immediate removal.
