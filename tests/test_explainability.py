import joblib
import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from app.ml.explainability import ModelExplainer
from app.ml.features import FEATURE_NAMES


@pytest.fixture
def trained_toy_model():
    X = np.random.uniform(0, 100, (40, 15))
    y = np.random.randint(0, 2, 40)
    clf = RandomForestClassifier(n_estimators=10, max_depth=3, random_state=42)
    clf.fit(X, y)
    return clf


def test_shap_tree_explainer_integration(trained_toy_model):
    explainer = ModelExplainer(model=trained_toy_model)
    assert explainer.shap_explainer is not None

    sample_features = {
        "avg_latency_ms": 650.0,
        "p95_latency_ms": 1200.0,
        "latency_trend": 2.5,
        "error_rate": 25.0,
        "timeout_rate": 10.0,
        "recent_consecutive_failures": 3.0,
        "availability": 82.0,
    }

    result = explainer.explain_shap(sample_features)
    assert result["method"] == "shap_tree_attribution"
    assert result["is_fallback"] is False
    assert len(result["top_contributing_features"]) <= 5
    assert len(result["all_features"]) == len(FEATURE_NAMES)
    assert "not causal mechanics" in result["interpretation_note"].lower()

    # Verify score direction and structure
    for item in result["all_features"]:
        assert "feature" in item
        assert "observed_value" in item
        assert "attribution_score" in item
        assert item["direction"] in ["increases_risk", "decreases_risk"]


def test_lime_tabular_explainer_integration(trained_toy_model):
    explainer = ModelExplainer(model=trained_toy_model)
    assert explainer.lime_explainer is not None

    sample_features = {
        "avg_latency_ms": 700.0,
        "p95_latency_ms": 1500.0,
        "error_rate": 30.0,
        "recent_consecutive_failures": 4.0,
    }

    result = explainer.explain_lime(sample_features, num_features=5)
    assert result["method"] == "lime_tabular_surrogate"
    assert result["is_fallback"] is False
    assert len(result["top_contributing_features"]) <= 5
    assert "linear approximation" in result["interpretation_note"].lower()
    assert "not causal mechanics" in result["interpretation_note"].lower()

    for item in result["top_contributing_features"]:
        assert "feature" in item
        assert "attribution_score" in item
        assert item["direction"] in ["increases_risk", "decreases_risk"]


def test_heuristic_fallback_when_no_model():
    explainer = ModelExplainer(model=None)
    assert explainer.shap_explainer is None
    assert explainer.lime_explainer is None

    sample_features = {
        "avg_latency_ms": 800.0,
        "error_rate": 20.0,
        "availability": 75.0,
        "recent_consecutive_failures": 3.0,
    }

    # Calling explain should transparently return heuristic with is_fallback=True
    result = explainer.explain(sample_features, risk_score=85.0, provenance="rules_baseline")
    assert result["method"] == "normalized_feature_attribution"
    assert result["is_fallback"] is True
    assert "heuristic fallback" in result["interpretation_note"].lower()
    assert len(result["top_contributing_features"]) > 0


def test_explain_method_selection(trained_toy_model):
    explainer = ModelExplainer(model=trained_toy_model)
    sample_features = {"error_rate": 15.0, "recent_consecutive_failures": 2.0}

    # Request SHAP
    shap_res = explainer.explain(sample_features, 60.0, "trained_model", method="shap")
    assert shap_res["method"] == "shap_tree_attribution"
    assert shap_res["is_fallback"] is False

    # Request LIME
    lime_res = explainer.explain(sample_features, 60.0, "trained_model", method="lime")
    assert lime_res["method"] == "lime_tabular_surrogate"
    assert lime_res["is_fallback"] is False

    # Request Heuristic explicitly
    heur_res = explainer.explain(sample_features, 60.0, "trained_model", method="heuristic")
    assert heur_res["method"] == "normalized_feature_attribution"
    assert heur_res["is_fallback"] is True


def test_missing_model_runtime_failure_handling():
    explainer = ModelExplainer(model=None)
    # Direct calls to explain_shap or explain_lime without model must raise RuntimeError
    with pytest.raises(RuntimeError):
        explainer.explain_shap({"error_rate": 5.0})

    with pytest.raises(RuntimeError):
        explainer.explain_lime({"error_rate": 5.0})
