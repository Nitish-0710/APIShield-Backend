import pytest

from app.ml.fairness import evaluate_fairness_by_group, generate_synthetic_fairness_report


def test_fairness_evaluation_native_libraries():
    y_true = [0, 1, 0, 1, 0, 1, 1, 0, 1, 0]
    y_pred = [0, 1, 0, 0, 0, 1, 1, 0, 0, 0]
    groups = ["tier_a", "tier_a", "tier_a", "tier_a", "tier_a", "tier_b", "tier_b", "tier_b", "tier_b", "tier_b"]

    result = evaluate_fairness_by_group(
        y_true=y_true,
        y_pred=y_pred,
        group_labels=groups,
        is_synthetic=False,
        privileged_group="tier_a",
    )

    assert result["status"] == "evaluated"
    assert "libraries" in result
    assert result["libraries"]["fairlearn"] == "native"
    assert result["libraries"]["aif360"] == "native"
    assert result["summary"]["groups_evaluated"] == 2
    assert "demographic_parity_ratio" in result["summary"]
    assert "equalized_odds_tpr_ratio" in result["summary"]
    assert result["aif360_metrics"] is not None
    assert "disparate_impact" in result["aif360_metrics"]
    assert "statistical_parity_difference" in result["aif360_metrics"]


def test_synthetic_fairness_report_disclaimer():
    report = generate_synthetic_fairness_report(sample_count=90)
    assert report["status"] == "evaluated"
    assert report["is_synthetic_demonstration"] is True
    assert "NOT constitute proof of human demographic fairness" in report["disclaimer"]
    assert "NOTICE:" in report["disclaimer"]
    assert len(report["groups"]) == 3
    assert "enterprise_tier" in report["groups"]
    assert "free_tier" in report["groups"]


def test_fairness_evaluation_invalid_inputs():
    # Mismatched lengths
    res1 = evaluate_fairness_by_group([1, 0], [1], ["a", "b"])
    assert res1["status"] == "error"

    # Empty inputs
    res2 = evaluate_fairness_by_group([], [], [])
    assert res2["status"] == "error"

    # Single group (cannot compute disparity)
    res3 = evaluate_fairness_by_group([1, 0, 1], [1, 0, 0], ["tier_a", "tier_a", "tier_a"])
    assert res3["status"] == "error"
    assert "at least two distinct groups" in res3["message"]
