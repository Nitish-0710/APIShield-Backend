import logging
from datetime import UTC, datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def evaluate_fairness_by_group(
    y_true: list[int],
    y_pred: list[int],
    group_labels: list[str],
    is_synthetic: bool = False,
    privileged_group: str | None = None,
) -> dict[str, Any]:
    """
    Evaluates group-based fairness metrics across sensitive attributes or infrastructure/client tiers.
    Integrates native Fairlearn (MetricFrame, selection_rate, TPR, FPR) and IBM AIF360
    (BinaryLabelDataset, disparate impact, statistical parity difference).

    Gracefully falls back to pure-Python group stats if native libraries encounter runtime issues.
    Clearly identifies synthetic data and includes non-demographic fairness disclaimers.
    """
    if len(y_true) != len(y_pred) or len(y_true) != len(group_labels) or not y_true:
        return {
            "status": "error",
            "message": "Mismatched lengths or empty input vectors for fairness evaluation.",
            "groups": {},
        }

    unique_groups = sorted(list(set(group_labels)))
    if len(unique_groups) < 2:
        return {
            "status": "error",
            "message": "Fairness evaluation requires at least two distinct groups.",
            "groups": {g: {"total_samples": len(y_true)} for g in unique_groups},
        }

    priv_group = privileged_group if privileged_group in unique_groups else unique_groups[0]
    group_stats: dict[str, dict[str, Any]] = {}

    fairlearn_used = False
    aif360_used = False
    aif360_metrics: dict[str, Any] = {}

    # 1. Native Fairlearn Integration
    try:
        from fairlearn.metrics import (
            MetricFrame,
            false_positive_rate,
            selection_rate,
            true_positive_rate,
        )

        metrics_dict = {
            "selection_rate": selection_rate,
            "true_positive_rate": true_positive_rate,
            "false_positive_rate": false_positive_rate,
        }
        mf = MetricFrame(
            metrics=metrics_dict,
            y_true=y_true,
            y_pred=y_pred,
            sensitive_features=group_labels,
        )

        for grp in unique_groups:
            # MetricFrame index corresponds to sensitive feature values
            grp_yt = [yt for yt, g in zip(y_true, group_labels) if g == grp]
            grp_yp = [yp for yp, g in zip(y_pred, group_labels) if g == grp]
            total = len(grp_yt)
            pos_pred = sum(1 for p in grp_yp if p == 1)

            sr = float(mf.by_group.loc[grp, "selection_rate"]) if grp in mf.by_group.index else 0.0
            tpr = float(mf.by_group.loc[grp, "true_positive_rate"]) if grp in mf.by_group.index else 0.0
            fpr = float(mf.by_group.loc[grp, "false_positive_rate"]) if grp in mf.by_group.index else 0.0

            group_stats[grp] = {
                "total_samples": total,
                "predicted_failures": pos_pred,
                "selection_rate": round(sr, 4),
                "true_positive_rate": round(0.0 if str(tpr) == "nan" else tpr, 4),
                "false_positive_rate": round(0.0 if str(fpr) == "nan" else fpr, 4),
            }
        fairlearn_used = True
    except Exception as e:
        logger.warning(f"Native Fairlearn calculation failed, using fallback: {e}")
        # Pure-Python group calculations
        for grp in unique_groups:
            grp_yt = [yt for yt, g in zip(y_true, group_labels) if g == grp]
            grp_yp = [yp for yp, g in zip(y_pred, group_labels) if g == grp]

            total = len(grp_yt)
            pos_pred = sum(1 for p in grp_yp if p == 1)
            selection_rate_val = pos_pred / total if total > 0 else 0.0

            tp = sum(1 for yt, yp in zip(grp_yt, grp_yp) if yt == 1 and yp == 1)
            fn = sum(1 for yt, yp in zip(grp_yt, grp_yp) if yt == 1 and yp == 0)
            fp = sum(1 for yt, yp in zip(grp_yt, grp_yp) if yt == 0 and yp == 1)
            tn = sum(1 for yt, yp in zip(grp_yt, grp_yp) if yt == 0 and yp == 0)

            actual_pos = tp + fn
            actual_neg = tn + fp

            tpr = tp / actual_pos if actual_pos > 0 else 0.0
            fpr = fp / actual_neg if actual_neg > 0 else 0.0

            group_stats[grp] = {
                "total_samples": total,
                "predicted_failures": pos_pred,
                "selection_rate": round(selection_rate_val, 4),
                "true_positive_rate": round(tpr, 4),
                "false_positive_rate": round(fpr, 4),
            }

    # 2. Native IBM AIF360 Integration
    try:
        import pandas as pd
        from aif360.datasets import BinaryLabelDataset
        from aif360.metrics import BinaryLabelDatasetMetric

        # Map privileged group to 1, others to 0
        bin_grp = [1 if g == priv_group else 0 for g in group_labels]
        df = pd.DataFrame({"label": y_pred, "group": bin_grp})

        bld = BinaryLabelDataset(
            df=df,
            label_names=["label"],
            protected_attribute_names=["group"],
            favorable_label=0,  # 0 = healthy (favorable outcome in failure prediction)
            unfavorable_label=1,
        )
        metric = BinaryLabelDatasetMetric(
            bld,
            privileged_groups=[{"group": 1}],
            unprivileged_groups=[{"group": 0}],
        )
        disp_impact = metric.disparate_impact()
        stat_par_diff = metric.statistical_parity_difference()

        aif360_metrics = {
            "privileged_group": priv_group,
            "disparate_impact": round(float(disp_impact), 4) if str(disp_impact) != "nan" else 1.0,
            "statistical_parity_difference": round(float(stat_par_diff), 4) if str(stat_par_diff) != "nan" else 0.0,
        }
        aif360_used = True
    except Exception as e:
        logger.warning(f"Native AIF360 calculation failed: {e}")

    # Disparity calculations (min / max ratio)
    rates = [s["selection_rate"] for s in group_stats.values()]
    tprs = [s["true_positive_rate"] for s in group_stats.values() if s["true_positive_rate"] > 0]

    demographic_parity_ratio = min(rates) / max(rates) if rates and max(rates) > 0 else 1.0
    equalized_odds_tpr_ratio = min(tprs) / max(tprs) if tprs else 1.0

    return {
        "status": "evaluated",
        "is_synthetic_demonstration": is_synthetic,
        "libraries": {
            "fairlearn": "native" if fairlearn_used else "fallback_python",
            "aif360": "native" if aif360_used else "fallback_python",
        },
        "disclaimer": (
            "NOTICE: APIShield monitoring observations do not track protected human attributes. "
            "This analysis demonstrates disparate impact and group parity across infrastructure or synthetic groups. "
            "Results do NOT constitute proof of human demographic fairness."
            if is_synthetic
            else "Group-level performance disparity across telemetry tiers."
        ),
        "evaluated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "demographic_parity_ratio": round(demographic_parity_ratio, 4),
            "equalized_odds_tpr_ratio": round(equalized_odds_tpr_ratio, 4),
            "groups_evaluated": len(unique_groups),
            "privileged_group": priv_group,
        },
        "aif360_metrics": aif360_metrics if aif360_used else None,
        "groups": group_stats,
    }


def generate_synthetic_fairness_report(sample_count: int = 120) -> dict[str, Any]:
    """
    Generates a reproducible synthetic fairness evaluation across client subscription tiers
    ('enterprise_tier', 'standard_tier', 'free_tier') for educational and audit verification.
    Clearly marks data as synthetic.
    """
    import random

    rng = random.Random(42)
    tiers = ["enterprise_tier", "standard_tier", "free_tier"]

    group_labels: list[str] = []
    y_true: list[int] = []
    y_pred: list[int] = []

    for i in range(sample_count):
        tier = tiers[i % len(tiers)]
        group_labels.append(tier)

        # Baseline failure rate higher on free tier due to rate limits
        base_fail_prob = 0.15 if tier == "enterprise_tier" else (0.25 if tier == "standard_tier" else 0.40)
        true_fail = 1 if rng.random() < base_fail_prob else 0
        y_true.append(true_fail)

        # Model prediction slightly noisy
        pred_prob = base_fail_prob * 0.9 if true_fail == 1 else 0.10
        pred = 1 if rng.random() < pred_prob else 0
        y_pred.append(pred)

    return evaluate_fairness_by_group(
        y_true=y_true,
        y_pred=y_pred,
        group_labels=group_labels,
        is_synthetic=True,
        privileged_group="enterprise_tier",
    )
