# Privacy, Occlusion, and Facial-State Improvement Plan

## 1. Privacy display mode

Goal: normal users should not see raw camera/video frames. They should see a skeleton-first view. Admin users can switch between skeleton-only and raw+overlay while validating the system.

Implemented direction:

- Default view is `skeleton`.
- Raw video is displayed only when the signed-in user has the `admin` role and chooses `raw`.
- The video element remains in the DOM so MediaPipe pose extraction and WebM chunk recording continue to work, but the raw pixels are visually hidden in skeleton mode.
- Log detail and reference videos are also hidden unless admin raw mode is enabled.

Limit:

- This is a UI privacy layer. For full compliance, server-side saved clips and admin APIs also need retention/permission policy review.

## 2. Lower-body occlusion augmentation

Problem: current stand/sit/lie and fall/non-fall decisions are weak when the lower body is hidden by a bed, desk, chair, blanket, or camera crop.

Direction:

- Keep original data unchanged.
- Generate lower-body-masked copies into a separate dataset folder.
- Use multiple mask start ratios, for example `0.55`, `0.62`, `0.70`, so the model sees mild, medium, and severe lower-body occlusion.
- Preserve class labels and group IDs with an `:lower_body_occlusion` suffix.
- During retraining, keep Group split by original video/person group so original and augmented clips do not leak across train/validation.

Added utility:

```bash
python3 /opt/app/project/main/scripts/create_lower_body_occlusion_augments.py \
  --input-root /opt/app/datasets/<source_class_dir> \
  --output-root /opt/app/datasets/fall_classification/lower_body_occlusion_augments \
  --labels stand,walk,run,sit,lie \
  --ratios 0.55,0.62,0.70 \
  --mask-color dark
```

Recommended validation:

- Train baseline model without occlusion augmentation.
- Train candidate model with occlusion augmentation.
- Evaluate both on a dedicated lower-body-occlusion holdout set.
- Track macro F1, per-class recall, and especially `stand/lie`, `sit/lie`, and fall false positive rate.

Training hook:

```bash
POSTURE_INCLUDE_LOWER_OCCLUSION=1 \
POSTURE_LOWER_OCCLUSION_LIMIT=80 \
POSTURE_LOWER_OCCLUSION_MANIFEST=/opt/app/datasets/fall_classification/lower_body_occlusion_augments/manifest.jsonl \
python3 /opt/app/project/main/scripts/retrain_xg_posture_sequence.py
```

The retraining script keeps augmented rows under the `external-lower-body-occlusion` source and preserves group IDs with `lowerocc:<label>:<source-group>`.

## 3. Facial-state parallel model

Feasibility: possible, but it should not be treated as a direct fall detector. Facial expression is a weak contextual signal and can be noisy because of camera angle, privacy masking, lighting, mask/hat occlusion, and personal differences.

Recommended architecture:

1. Face/upper-body state extractor runs in parallel with current fall RF and posture model.
2. It outputs small, non-identifying signals:
   - face visible / not visible
   - eyes closed or drowsiness cue
   - distress/pain expression cue
   - gaze/head-down instability cue
   - confidence and occlusion state
3. A separate temporal risk model consumes:
   - current fall score
   - posture/action state
   - motion instability
   - lower-body occlusion confidence
   - facial-state cues
4. The final output explains facial-state cues only as supporting evidence, not as the sole reason for fall prediction.

Needed data:

- Consent-cleared face/upper-body footage from the target environment.
- Labels for near-miss, dizziness, distress/pain, eyes-closed/drowsy, normal baseline.
- Non-event negative examples so expression cues do not create excessive false alarms.

Limit:

- A "true prediction" model needs seconds-to-minutes lead time labels, not just fall/non-fall clips.
- Expression alone cannot reliably predict a fall. It can improve risk ranking when combined with gait instability, posture transition, and environment context.

Recommended next step:

- Start with a shadow-only facial-state module that logs cues but does not affect the emergency decision.
- After collecting enough labeled data, calibrate its contribution to the risk model and report false alarm/hour.
