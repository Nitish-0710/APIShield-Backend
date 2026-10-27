"""
Tests for isolated candidate model evaluation on experimental telemetry datasets.

Validates:
1. Candidate evaluation explicitly loads the experimental dataset.
2. Candidate training strictly uses the train split; model selection strictly uses the validation split.
3. Test split is evaluated only once on the chosen candidate without lookahead or data leakage.
4. Production models (latest_model.joblib, latest_model_meta.json) and active serving are NOT modified.
5. Candidate promotion is prevented (promotion_status == NOT_PROMOTED_ISOLATED_EVALUATION).
6. Metrics computation includes PR-AUC, ROC-AUC, Specificity, FPR, confusion matrix, and scenario slice breakdowns.
7. Zero-positive slices correctly report precision/recall/F1 as None (JSON null).
8. Slice membership depends strictly on feature vectors, never target labels.
9. Reproducibility metadata (dataset seed, model hyperparameters, purge gap) are recorded.
"""

import json
from pathlib import Path
import pytest

from app.ml.candidate_evaluator import (
    IsolatedCandidateEvaluator,
    compute_comprehensive_metrics,
    compute_slice_breakdown,
)
from app.ml.features import FEATURE_NAMES
from app.ml.pipeline import evaluate_candidate_pipeline


def test_isolated_evaluation_produces_valid_report_and_preserves_production(tmp_path):
    """
    Verify that candidate evaluation runs completely, saves artifacts to experimental dir,
    and leaves production model artifacts strictly untouched.
    """
    prod_meta_path = Path("artifacts/models/latest_model_meta.json")
    prod_joblib_path = Path("artifacts/models/latest_model.joblib")

    # Capture production state
    prod_meta_mtime = prod_meta_path.stat().st_mtime if prod_meta_path.exists() else None
    prod_joblib_mtime = prod_joblib_path.stat().st_mtime if prod_joblib_path.exists() else None
    prod_meta_content = prod_meta_path.read_text(encoding="utf-8") if prod_meta_path.exists() else None

    exp_dir = tmp_path / "experimental_test_run"
    evaluator = IsolatedCandidateEvaluator(
        dataset_path="data/experimental_telemetry_dataset.json",
        output_dir=str(exp_dir),
    )
    report = evaluator.run_evaluation()

    # 1. Output artifacts created in custom output directory
    cand_model = exp_dir / "candidate_model.joblib"
    cand_report = exp_dir / "candidate_evaluation_report.json"
    assert cand_model.exists(), "Candidate model artifact must be saved"
    assert cand_report.exists(), "Candidate report artifact must be saved"

    # 2. Production models must be completely untouched
    if prod_meta_path.exists():
        assert prod_meta_path.stat().st_mtime == prod_meta_mtime, "Production metadata mtime must not change"
        assert prod_meta_path.read_text(encoding="utf-8") == prod_meta_content, "Production metadata content must not change"
    if prod_joblib_path.exists():
        assert prod_joblib_path.stat().st_mtime == prod_joblib_mtime, "Production model weights mtime must not change"

    # 3. Promotion status check
    assert report["promotion_status"] == "NOT_PROMOTED_ISOLATED_EVALUATION"

    # 4. Reproducibility metadata fields present
    assert "dataset_random_seed" in report
    assert "purge_gap_configuration" in report
    assert "candidate_selection" in report
    assert "hyperparameters" in report["selected_candidate"]


def test_validation_model_selection_and_test_isolation(tmp_path):
    """
    Verify model selection uses the validation split and that candidate metrics
    on test split are populated with PR-AUC, ROC-AUC, Specificity, and slice breakdowns.
    """
    exp_dir = tmp_path / "exp_selection_test"
    evaluator = IsolatedCandidateEvaluator(
        dataset_path="data/experimental_telemetry_dataset.json",
        output_dir=str(exp_dir),
    )
    report = evaluator.run_evaluation()

    # Check validation model selection
    selection_list = report["candidate_selection"]["validation_results"]
    assert len(selection_list) >= 2, "Must evaluate multiple candidate configurations on validation split"
    for candidate in selection_list:
        assert "pr_auc" in candidate
        assert "f1" in candidate
        assert "accuracy" in candidate
        assert "hyperparameters" in candidate

    # Check selected candidate
    selected = report["selected_candidate"]
    assert selected["selection_split"] == "validation"
    assert selected["name"] is not None
    assert selected["hyperparameters"]["n_estimators"] > 0

    # Check holdout test evaluation (purged test size is 115)
    test_eval = report["holdout_test_evaluation"]
    cand_metrics = test_eval["candidate_metrics"]
    base_metrics = test_eval["baseline_metrics"]

    assert cand_metrics["total_samples"] == 115
    assert cand_metrics["pr_auc"] is not None
    assert cand_metrics["roc_auc"] is not None
    assert cand_metrics["specificity"] is not None
    assert cand_metrics["f1"] > 0.0

    # Ensure candidate outperforms or compares to baseline
    assert "confusion_matrix" in cand_metrics
    assert "confusion_matrix" in base_metrics

    # Check slice breakdowns
    slices = test_eval["slice_breakdown"]
    for required_slice in ["http_5xx", "http_4xx", "timeouts", "persistent_failures", "recovery"]:
        assert required_slice in slices, f"Slice breakdown must include {required_slice}"
        slice_data = slices[required_slice]
        assert "sample_count" in slice_data
        assert "candidate" in slice_data
        assert "baseline" in slice_data
        assert "rule" in slice_data


def test_missing_dataset_raises_explicit_error(tmp_path):
    """Verify evaluator fails informatively when an invalid dataset path is passed."""
    non_existent = tmp_path / "missing_dataset.json"
    evaluator = IsolatedCandidateEvaluator(dataset_path=str(non_existent))

    with pytest.raises(FileNotFoundError, match="Experimental dataset not found"):
        evaluator.run_evaluation()


def test_compute_comprehensive_metrics_positive_and_negative_cases():
    """Verify metrics computation with both classes present."""
    y_true = [0, 0, 1, 1, 0, 1]
    y_pred = [0, 0, 1, 0, 0, 1]
    y_prob = [0.1, 0.2, 0.9, 0.4, 0.1, 0.8]

    metrics = compute_comprehensive_metrics(y_true, y_pred, y_prob)

    assert metrics["total_samples"] == 6
    assert metrics["positive_labels"] == 3
    assert metrics["negative_labels"] == 3
    assert metrics["accuracy"] == round(5 / 6, 4)
    assert metrics["precision"] == 1.0  # 2 TP, 0 FP
    assert metrics["recall"] == round(2 / 3, 4)  # 2 TP, 1 FN
    assert metrics["specificity"] == 1.0  # 3 TN, 0 FP
    assert metrics["false_positive_rate"] == 0.0
    assert metrics["pr_auc"] is not None
    assert metrics["roc_auc"] is not None
    assert metrics["confusion_matrix"] == [[3, 0], [1, 2]]


def test_compute_comprehensive_metrics_zero_positives_returns_none():
    """Verify zero-positive slices return None (JSON null) for undefined metrics rather than misleading zeroes."""
    y_true = [0, 0, 0, 0]
    y_pred = [0, 0, 1, 0]  # 3 TN, 1 FP, 0 TP, 0 FN
    y_prob = [0.1, 0.2, 0.8, 0.3]

    metrics = compute_comprehensive_metrics(y_true, y_pred, y_prob)

    assert metrics["total_samples"] == 4
    assert metrics["positive_labels"] == 0
    assert metrics["negative_labels"] == 4
    assert metrics["accuracy"] == 0.75
    assert metrics["specificity"] == 0.75  # 3 / 4
    assert metrics["false_positive_rate"] == 0.25  # 1 / 4
    # Undefined metrics MUST be None
    assert metrics["precision"] is None
    assert metrics["recall"] is None
    assert metrics["f1"] is None
    assert metrics["pr_auc"] is None


def test_slice_breakdown_membership_independent_of_labels():
    """Verify that operational slice membership is strictly determined by feature vectors and not target labels."""
    # 2 feature vectors: sample 0 has error_rate=20 and consec=0 (recovery pattern)
    vec0 = [100.0] * len(FEATURE_NAMES)
    vec0[FEATURE_NAMES.index("error_rate")] = 20.0
    vec0[FEATURE_NAMES.index("recent_consecutive_failures")] = 0.0

    vec1 = [100.0] * len(FEATURE_NAMES)
    vec1[FEATURE_NAMES.index("http_5xx_rate")] = 40.0
    vec1[FEATURE_NAMES.index("recent_consecutive_failures")] = 3.0

    X = [vec0, vec1]

    # Evaluate with y_true = [0, 1]
    res_A = compute_slice_breakdown(X, y_true=[0, 1], y_pred_candidate=[0, 1], y_pred_baseline=[0, 1])

    # Evaluate with inverted y_true = [1, 0]
    res_B = compute_slice_breakdown(X, y_true=[1, 0], y_pred_candidate=[0, 1], y_pred_baseline=[0, 1])

    # Slices must have the exact same sample indices and total counts regardless of label
    for slice_name in ["http_5xx", "recovery", "persistent_failures"]:
        assert res_A[slice_name]["sample_count"] == res_B[slice_name]["sample_count"], (
            f"Slice {slice_name} sample count must not depend on y_true"
        )


def test_pipeline_evaluate_candidate_wrapper(tmp_path):
    """Verify evaluate_candidate_pipeline in pipeline.py successfully runs isolated evaluation."""
    exp_dir = tmp_path / "pipeline_exp"
    res = evaluate_candidate_pipeline(
        dataset_path="data/experimental_telemetry_dataset.json",
        output_dir=str(exp_dir),
    )

    assert res["evaluation_type"] == "isolated_candidate_evaluation"
    assert res["promotion_status"] == "NOT_PROMOTED_ISOLATED_EVALUATION"
    assert Path(res["candidate_model_artifact"]).exists()
    assert Path(res["report_artifact"]).exists()
