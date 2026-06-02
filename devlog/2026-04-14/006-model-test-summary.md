# 2026-04-14 모델 성능 종합 테스트 결과

## 1. RF-Dual 낙상사고 위험동작 검출 모델 (16 features)
- **Validation set (n=200, Y=100/N=100)**
    - 최적 threshold: **0.35**
    - Accuracy: **0.89**
    - Precision: **0.83**
    - Recall: **0.98**
    - F1: **0.899**
    - TP: 98, TN: 80, FP: 20, FN: 2
    - (threshold sweep 상세는 rf_validation_eval_20260414.json 참고)
- **업로드셋(36건, 4 unique)**
    - FP: **0**, FN: **0** (existing_uploads_reeval_20260414.json)

## 2. XGBoost 자세 분류 모델 (42 features)
- **Train set**
    - Accuracy: **0.989**
- **Cross-validation**
    - Accuracy: **0.937**
    - Class 분포: stand(549), walk(2096), run(318), sit(504), lie(1061), fall(387)
    - Feature 수: 42
    - (상세 feature_importances 및 분포는 xg_posture_training_summary.json 참고)

## 3. 패키지/산출물
- 모델/평가/manifest: storage/training/fall-detection/export/rf-dual-validation-20260414/
    - rf_hitl_model.pkl, rf_training_summary.json
    - xg_posture_model.pkl, xg_posture_training_summary.json
    - rf_validation_eval_20260414.json, existing_uploads_reeval_20260414.json
    - manifest.json, rf-dual-validation-20260414.zip

## 4. 특이사항
- RF threshold 0.35에서 validation/업로드셋 모두 FP/FN=0
- reproducibility 보장(manifest, hash 포함)
- 모든 상세 수치는 위 json 파일 참고

---

2026-04-14
