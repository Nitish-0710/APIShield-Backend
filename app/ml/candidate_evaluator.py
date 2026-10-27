"""
Isolated candidate evaluation for experimental telemetry datasets.

Provides a safe evaluation workflow that:
1. Loads an experimental dataset artifact (e.g. experimental_telemetry_dataset.json).
2. Fits candidate models ONLY on the chronological train split.
3. Performs candidate model selection strictly using the validation split.
4. Evaluates the selected candidate model once on the untouched holdout test split.
5. Computes comprehensive classification and class-imbalance metrics (PR-AUC, ROC-AUC, Specificity, FPR).
6. Handles zero-positive slices safely by reporting mathematically undefined metrics as None (JSON null).
7. Evaluates the RuleBasedBaseline on the identical val/test splits for transparent comparison.
8. Computes operational slice metrics based purely on prediction-time features (never target labels).
9. Records dataset random seed, complete model hyperparameters, selection metrics, and purge gap configuration.
10. Persists candidate artifacts strictly under artifacts/experimental/ without modifying production models.
"""

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.ml.features import FEATURE_NAMES
from app.ml.model import RuleBasedBaseline


def compute_comprehensive_metrics(
    y_true: list[int] | np.ndarray,
    y_pred: list[int] | np.ndarray,
    y_prob: Optional[list[float] | np.ndarray] = None,
) -> dict[str, Any]:
    """
    Computes standard classification metrics plus class-imbalance metrics (PR-AUC, ROC-AUC),
    specificity, and false-positive rate. Reports undefined metrics as None (JSON null).
    """
    y_t = np.array(y_true, dtype=int)
    y_p = np.array(y_pred, dtype=int)

    total = len(y_t)
    if total == 0:
        return {
            "total_samples": 0,
            "positive_labels": 0,
            "negative_labels": 0,
            "accuracy": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "pr_auc": None,
            "roc_auc": None,
            "specificity": None,
            "false_positive_rate": None,
            "confusion_matrix": [[0, 0], [0, 0]],
        }

    cm = confusion_matrix(y_t, y_p, labels=[0, 1]).tolist()
    tn, fp = cm[0]
    fn, tp = cm[1]

    acc = float(accuracy_score(y_t, y_p))
    pos_count = int(sum(y_t))
    neg_count = int(total - pos_count)

    # Specificity and False Positive Rate
    specificity = round(tn / (tn + fp), 4) if (tn + fp) > 0 else None
    fpr = round(fp / (tn + fp), 4) if (tn + fp) > 0 else None

    # For sets with no positive labels, precision/recall/F1/PR-AUC are mathematically undefined.
    if pos_count == 0:
        prec = None
        rec = None
        f1 = None
        pr_auc = None
        roc_auc = None
    else:
        prec = round(float(precision_score(y_t, y_p, zero_division=0)), 4)
        rec = round(float(recall_score(y_t, y_p, zero_division=0)), 4)
        f1 = round(float(f1_score(y_t, y_p, zero_division=0)), 4)

        pr_auc = None
        roc_auc = None
        if y_prob is not None:
            y_score = np.array(y_prob, dtype=float)
            if len(np.unique(y_t)) > 1:
                try:
                    pr_auc = round(float(average_precision_score(y_t, y_score)), 4)
                    roc_auc = round(float(roc_auc_score(y_t, y_score)), 4)
                except Exception:
                    pass
            elif pos_count > 0:
                pr_auc = prec

    return {
        "total_samples": total,
        "positive_labels": pos_count,
        "negative_labels": neg_count,
        "accuracy": round(acc, 4),
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "specificity": specificity,
        "false_positive_rate": fpr,
        "confusion_matrix": cm,
    }


def compute_slice_breakdown(
    X: list[list[float]],
    y_true: list[int],
    y_pred_candidate: list[int],
    y_pred_baseline: list[int],
) -> dict[str, Any]:
    """
    Computes performance breakdown on operational slices defined strictly using
    features available at prediction time (NEVER using ground-truth target labels):
    - http_5xx: Observations with recent 5xx server errors in feature window (http_5xx_rate > 0)
    - http_4xx: Observations with recent 4xx client errors in feature window (http_4xx_rate > 0)
    - timeouts: Observations with recent timeouts in feature window (timeout_rate > 0)
    - persistent_failures: Multiple consecutive failures or high error rate (consec >= 2 or error_rate >= 50%)
    - recovery: Historical errors in sliding window (error_rate > 0) but the latest probe passed
                (recent_consecutive_failures == 0), observable purely at prediction time.
    """
    idx_5xx = FEATURE_NAMES.index("http_5xx_rate")
    idx_4xx = FEATURE_NAMES.index("http_4xx_rate")
    idx_timeout = FEATURE_NAMES.index("timeout_rate")
    idx_consec = FEATURE_NAMES.index("recent_consecutive_failures")
    idx_err = FEATURE_NAMES.index("error_rate")

    slice_rules = {
        "http_5xx": "http_5xx_rate > 0.0",
        "http_4xx": "http_4xx_rate > 0.0",
        "timeouts": "timeout_rate > 0.0",
        "persistent_failures": "recent_consecutive_failures >= 2.0 or error_rate >= 50.0",
        "recovery": "error_rate > 0.0 and recent_consecutive_failures == 0.0",
    }

    slices: dict[str, list[int]] = {k: [] for k in slice_rules}

    for i, vec in enumerate(X):
        if vec[idx_5xx] > 0.0:
            slices["http_5xx"].append(i)
        if vec[idx_4xx] > 0.0:
            slices["http_4xx"].append(i)
        if vec[idx_timeout] > 0.0:
            slices["timeouts"].append(i)
        if vec[idx_consec] >= 2.0 or vec[idx_err] >= 50.0:
            slices["persistent_failures"].append(i)
        if vec[idx_err] > 0.0 and vec[idx_consec] == 0.0:
            slices["recovery"].append(i)

    results: dict[str, Any] = {}
    for slice_name, indices in slices.items():
        if not indices:
            results[slice_name] = {
                "sample_count": 0,
                "positive_labels": 0,
                "negative_labels": 0,
                "rule": slice_rules[slice_name],
                "status": "no_samples",
            }
            continue

        slice_y = [y_true[i] for i in indices]
        slice_cand = [y_pred_candidate[i] for i in indices]
        slice_base = [y_pred_baseline[i] for i in indices]

        cand_metrics = compute_comprehensive_metrics(slice_y, slice_cand)
        base_metrics = compute_comprehensive_metrics(slice_y, slice_base)

        results[slice_name] = {
            "sample_count": len(indices),
            "positive_labels": cand_metrics["positive_labels"],
            "negative_labels": cand_metrics["negative_labels"],
            "rule": slice_rules[slice_name],
            "candidate": {
                "accuracy": cand_metrics["accuracy"],
                "precision": cand_metrics["precision"],
                "recall": cand_metrics["recall"],
                "f1": cand_metrics["f1"],
                "specificity": cand_metrics["specificity"],
                "false_positive_rate": cand_metrics["false_positive_rate"],
                "confusion_matrix": cand_metrics["confusion_matrix"],
            },
            "baseline": {
                "accuracy": base_metrics["accuracy"],
                "precision": base_metrics["precision"],
                "recall": base_metrics["recall"],
                "f1": base_metrics["f1"],
                "specificity": base_metrics["specificity"],
                "false_positive_rate": base_metrics["false_positive_rate"],
                "confusion_matrix": base_metrics["confusion_matrix"],
            },
        }

    return results


class IsolatedCandidateEvaluator:
    """
    Evaluator that safely trains candidate models and benchmarks on experimental data
    completely isolated from production models and serving infrastructure.
    """

    def __init__(
        self,
        dataset_path: str = "data/experimental_telemetry_dataset.json",
        output_dir: str = "artifacts/experimental",
    ):
        self.dataset_path = Path(dataset_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.baseline = RuleBasedBaseline()

    def run_evaluation(self) -> dict[str, Any]:
        """
        Executes isolated candidate training, validation model selection, and holdout test evaluation.
        """
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Experimental dataset not found at: {self.dataset_path}")

        with open(self.dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        if dataset.get("status") != "ready":
            raise ValueError(f"Dataset status is not ready: {dataset.get('status')}")

        if "train" not in dataset or "val" not in dataset or "test" not in dataset:
            raise ValueError("Dataset must contain 3-way train, val, and test splits.")

        X_train = dataset["train"]["X"]
        y_train = dataset["train"]["y"]
        X_val = dataset["val"]["X"]
        y_val = dataset["val"]["y"]
        X_test = dataset["test"]["X"]
        y_test = dataset["test"]["y"]

        # Step 1: Candidate Model Configurations with explicit hyperparameters
        candidate_configs = [
            {
                "name": "RF_balanced_d5_n50",
                "params": {
                    "n_estimators": 50,
                    "max_depth": 5,
                    "class_weight": "balanced",
                    "random_state": 42,
                },
                "model": RandomForestClassifier(
                    n_estimators=50, max_depth=5, class_weight="balanced", random_state=42
                ),
            },
            {
                "name": "RF_balanced_d6_n80",
                "params": {
                    "n_estimators": 80,
                    "max_depth": 6,
                    "class_weight": "balanced",
                    "random_state": 42,
                },
                "model": RandomForestClassifier(
                    n_estimators=80, max_depth=6, class_weight="balanced", random_state=42
                ),
            },
            {
                "name": "RF_unweighted_d5_n50",
                "params": {
                    "n_estimators": 50,
                    "max_depth": 5,
                    "class_weight": None,
                    "random_state": 42,
                },
                "model": RandomForestClassifier(
                    n_estimators=50, max_depth=5, class_weight=None, random_state=42
                ),
            },
        ]

        # Step 2: Fit on Train split and evaluate on Validation split ONLY
        val_selection_results = []
        for cfg in candidate_configs:
            clf = cfg["model"]
            clf.fit(X_train, y_train)

            val_preds = clf.predict(X_val).tolist()
            val_probs = clf.predict_proba(X_val)[:, 1].tolist()
            metrics = compute_comprehensive_metrics(y_val, val_preds, val_probs)

            val_selection_results.append({
                "name": cfg["name"],
                "params": cfg["params"],
                "model": clf,
                "metrics": metrics,
            })

        # Selection criterion: Highest Validation PR-AUC, breaking ties with F1
        best_candidate = max(
            val_selection_results,
            key=lambda item: (item["metrics"]["pr_auc"] or 0.0, item["metrics"]["f1"] or 0.0),
        )
        selected_model = best_candidate["model"]
        selected_name = best_candidate["name"]

        # Step 3: Evaluate Baseline on Validation Split
        baseline_val_preds = self.baseline.predict(X_val)
        baseline_val_metrics = compute_comprehensive_metrics(y_val, baseline_val_preds)

        # Step 4: Final Evaluation on the Untouched Holdout Test Split
        test_preds = selected_model.predict(X_test).tolist()
        test_probs = selected_model.predict_proba(X_test)[:, 1].tolist()
        candidate_test_metrics = compute_comprehensive_metrics(y_test, test_preds, test_probs)

        # Baseline evaluation on the same test split
        baseline_test_preds = self.baseline.predict(X_test)
        baseline_test_metrics = compute_comprehensive_metrics(y_test, baseline_test_preds)

        # Step 5: Slice Breakdowns on Holdout Test Split (feature-defined, no target leakage)
        test_slice_breakdown = compute_slice_breakdown(
            X=X_test,
            y_true=y_test,
            y_pred_candidate=test_preds,
            y_pred_baseline=baseline_test_preds,
        )

        val_slice_breakdown = compute_slice_breakdown(
            X=X_val,
            y_true=y_val,
            y_pred_candidate=selected_model.predict(X_val).tolist(),
            y_pred_baseline=baseline_val_preds,
        )

        # Step 6: Feature Importances
        feature_importances = dict(
            zip(FEATURE_NAMES, [round(float(v), 5) for v in selected_model.feature_importances_])
        )

        # Step 7: Compile final evaluation report with rich reproducibility metadata
        timestamp = datetime.now(UTC).isoformat()
        dataset_meta = dataset.get("metadata", {})
        purge_gap = dataset.get("purge_gap", dataset_meta.get("purge_gap", 0))
        purged_samples = dataset.get("purged_count", dataset_meta.get("purged_samples", 0))

        report = {
            "evaluation_type": "isolated_candidate_evaluation",
            "evaluated_at": timestamp,
            "dataset_path": str(self.dataset_path),
            "dataset_random_seed": dataset_meta.get("seed", 42),
            "purge_gap_configuration": {
                "purge_gap_samples": purge_gap,
                "purged_samples_total": purged_samples,
                "rationale": "Embargoes boundary samples between train/val and val/test to prevent sliding-window overlap and target contamination.",
            },
            "sample_counts": {
                "train": len(y_train),
                "validation": len(y_val),
                "test": len(y_test),
                "total_retained": len(y_train) + len(y_val) + len(y_test),
                "total_unpurged_samples": dataset.get("total_unpurged_samples", len(y_train) + len(y_val) + len(y_test)),
            },
            "candidate_selection": {
                "selection_metric": "pr_auc (with f1 tie-breaker)",
                "selection_split": "validation",
                "validation_results": [
                    {
                        "name": r["name"],
                        "hyperparameters": r["params"],
                        "f1": r["metrics"]["f1"],
                        "pr_auc": r["metrics"]["pr_auc"],
                        "roc_auc": r["metrics"]["roc_auc"],
                        "accuracy": r["metrics"]["accuracy"],
                        "precision": r["metrics"]["precision"],
                        "recall": r["metrics"]["recall"],
                        "specificity": r["metrics"]["specificity"],
                    }
                    for r in val_selection_results
                ],
            },
            "selected_candidate": {
                "name": selected_name,
                "hyperparameters": best_candidate["params"],
                "selection_split": "validation",
                "validation_metrics": best_candidate["metrics"],
                "baseline_validation_metrics": baseline_val_metrics,
            },
            "holdout_test_evaluation": {
                "candidate_metrics": candidate_test_metrics,
                "baseline_metrics": baseline_test_metrics,
                "slice_breakdown": test_slice_breakdown,
            },
            "validation_slice_breakdown": val_slice_breakdown,
            "feature_importances": feature_importances,
            "promotion_status": "NOT_PROMOTED_ISOLATED_EVALUATION",
            "production_impact": "None. Production models and database untouched.",
        }

        # Save Candidate Artifacts strictly under output_dir
        candidate_model_path = self.output_dir / "candidate_model.joblib"
        report_path = self.output_dir / "candidate_evaluation_report.json"

        joblib.dump(selected_model, candidate_model_path)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        report["candidate_model_artifact"] = str(candidate_model_path)
        report["report_artifact"] = str(report_path)

        return report


if __name__ == "__main__":
    evaluator = IsolatedCandidateEvaluator()
    rep = evaluator.run_evaluation()
    print("Isolated Candidate Evaluation Complete:")
    print(f"Selected Model: {rep['selected_candidate']['name']}")
    print(f"Hyperparameters: {rep['selected_candidate']['hyperparameters']}")
    print(f"Purge Gap: {rep['purge_gap_configuration']['purge_gap_samples']} samples")
    print(f"Test F1: {rep['holdout_test_evaluation']['candidate_metrics']['f1']}")
    print(f"Test PR-AUC: {rep['holdout_test_evaluation']['candidate_metrics']['pr_auc']}")
    print(f"Test Accuracy: {rep['holdout_test_evaluation']['candidate_metrics']['accuracy']}")
    print(f"Test Specificity: {rep['holdout_test_evaluation']['candidate_metrics']['specificity']}")
    print(f"Report saved to: {rep['report_artifact']}")
