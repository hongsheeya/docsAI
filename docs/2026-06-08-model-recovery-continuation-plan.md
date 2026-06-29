# Model recovery and continuation plan

## Current truth

The dashboard must not show emergency artifacts as production models. A model is
operational only when its summary is `ready: true` and it was trained or
validated from real data.

Current real-ready state:

- XG-Posture base: available.
- RF-Fall v2: missing real trained artifact.
- AI-Hub 82 facial emotion: missing real trained artifact.
- AI-Hub 173 driver state: missing real trained artifact.
- XG-Posture occlusion auxiliary: missing real trained artifact.

## Durable paths

- Dataset root: `/opt/app/datasets` -> `/mnt/data/wiz/datasets`
- Model storage: `/opt/app/storage` -> `/mnt/data/wiz/storage`
- Model binaries: `/opt/app/models` -> `/mnt/data/wiz/models`
- AI-Hub shell mirror: `/mnt/data/wiz/tools/aihubshell`

`/opt/app/run.sh` recreates these paths on boot.

## Recovery priority

1. AI-Hub 173 driver state
   - Smallest source size.
   - Training script reads zip files directly.
   - First target: recover a real status/facial-state auxiliary model.

2. AI-Hub 82 facial emotion
   - 7-class label/source subset first.
   - Training script reads zip files directly.
   - First target: recover the baseline 7-class expression model.
   - Next target: compare with distress-binary/operational-clean heads for fall
     auxiliary use.

3. XG-Posture occlusion auxiliary
   - Train only after AI-Hub 173 recovery starts or finishes, so CPU is not
     overloaded.
   - Include both lower-body occlusion and vertical/side occlusion.
   - Use as an auxiliary model only when the main posture model is uncertain,
     lower-body visibility is low, or side/vertical occlusion is suspected.

4. RF-Fall v2
   - AI-Hub 71641 compressed source is large.
   - Full extraction plus compressed archives can exceed persistent storage.
   - Do not blindly unzip everything. Build a zip-aware or staged extraction
     feature builder, then train RF-Fall v2 from real sampled videos.

## No blind version bump rule

If a model does not beat the active candidate after several runs, do not keep
incrementing version numbers with the same recipe.

Switch one of these axes instead:

- Data: add missing hard cases, rebalance only the confused boundary, or remove
  noisy labels.
- Label policy: for AI-Hub 82, compare 7-class expression vs distress-binary vs
  operational-clean labels.
- Feature policy: add/remove features based on confusion, not by bulk expansion.
- Validation policy: enforce group split and separate hard-case validation.
- Runtime policy: only promote if the model improves the production decision,
  not just an isolated training metric.

## Promotion policy

Do not replace active runtime artifacts just because a training job completed.

Promote only when:

- The model loads successfully.
- Summary has `ready: true`.
- Macro F1 or the operational target metric improves.
- Weak-class or hard-case validation does not regress materially.
- Runtime cost is acceptable for the current server.

Before promotion:

- Keep previous active artifact as a timestamped backup.
- Copy the promoted artifact into `/mnt/data/wiz/storage`.
- Keep project mirror files only as convenience copies, not as the source of
  truth.

## Monitoring commands

Download:

```bash
/mnt/data/wiz/datasets/aihub_recovery_status.sh
```

Download + training + active summaries:

```bash
/mnt/data/wiz/datasets/model_recovery_status.sh
```

Raw process check with API key masked:

```bash
ps aux | grep -E 'aihubshell|model_recovery|train_' | grep -v grep | sed -E "s/-aihubapikey [^ ]+/-aihubapikey ***MASKED***/g"
```

## Next engineering work

1. Let AI-Hub 173 train/validation source finish.
2. Validate AI-Hub 173 rows with dry-run and train MobileNetV3 CPU recovery
   model.
3. Let AI-Hub 82 source subset download and train 7-class baseline.
4. Run distress-binary AI-Hub 82 candidate only after the baseline is recovered.
5. Retrain XG-Posture occlusion auxiliary with lower+vertical occlusion.
6. Add RF-Fall v2 zip-aware/staged extraction before attempting 71641 full
   feature generation.
