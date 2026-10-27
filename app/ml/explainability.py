import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from app.ml.features import FEATURE_NAMES

logger = logging.getLogger(__name__)


class ModelExplainer:
    """
    Computes feature contributions and explainability for API failure predictions.
    Supports genuine SHAP TreeExplainer, genuine LIME LimeTabularExplainer,
    and a robust normalized heuristic baseline fallback.
    Clearly distinguishes genuine ML explanations from heuristic fallbacks via `is_fallback`.
    """

    def __init__(
        self,
        model: Any | None = None,
        feature_names: list[str] | None = None,
        background_data: Any | None = None,
    ):
        self.model = model
        self.feature_names = list(feature_names or FEATURE_NAMES)
        self.background_data = background_data
        self.shap_explainer = None
        self.lime_explainer = None
        self._init_shap()
        self._init_lime()

    def _init_shap(self) -> None:
        if self.model is None:
            self.shap_explainer = None
            return
        try:
            import shap
            self.shap_explainer = shap.TreeExplainer(self.model)
        except Exception as e:
            logger.warning(f"Could not initialize SHAP TreeExplainer: {e}")
            self.shap_explainer = None

    def _get_background_matrix(self) -> np.ndarray:
        if self.background_data is not None:
            return np.asarray(self.background_data, dtype=np.float64)

        # Try loading training data from telemetry_dataset.json
        data_path = Path("data/telemetry_dataset.json")
        if data_path.exists():
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    ds = json.load(f)
                train_x = ds.get("train", {}).get("X", [])
                if train_x and len(train_x) >= 5:
                    return np.asarray(train_x[:100], dtype=np.float64)
            except Exception:
                pass

        # Realistic default baseline matrix across the 15 features
        np.random.seed(42)
        rows = []
        for _ in range(50):
            rows.append([
                float(np.random.uniform(50.0, 300.0)),   # avg_latency_ms
                float(np.random.uniform(100.0, 600.0)),  # p95_latency_ms
                float(np.random.uniform(0.8, 2.0)),     # latency_trend
                float(np.random.uniform(0.0, 20.0)),    # error_rate
                float(np.random.uniform(0.0, 10.0)),    # timeout_rate
                float(np.random.uniform(0.0, 15.0)),    # http_4xx_rate
                float(np.random.uniform(0.0, 15.0)),    # http_5xx_rate
                float(np.random.uniform(85.0, 100.0)),  # availability
                float(np.random.randint(0, 4)),         # recent_consecutive_failures
                float(np.random.uniform(1.0, 50.0)),    # request_rate
                float(np.random.uniform(5.0, 80.0)),    # jitter_ms
                float(np.random.uniform(0.0, 2.5)),     # status_entropy
                float(np.random.uniform(0.0, 5.0)),     # anomaly_score
                float(np.random.uniform(0.5, 3.0)),     # burst_multiplier
                float(np.random.uniform(0.0, 1.0)),     # recovery_ratio
            ])
        return np.asarray(rows, dtype=np.float64)

    def _init_lime(self) -> None:
        if self.model is None or not hasattr(self.model, "predict_proba"):
            self.lime_explainer = None
            return
        try:
            import lime
            import lime.lime_tabular
            bg = self._get_background_matrix()
            self.lime_explainer = lime.lime_tabular.LimeTabularExplainer(
                training_data=bg,
                feature_names=self.feature_names,
                class_names=["healthy", "failing"],
                mode="classification",
                random_state=42,
            )
        except Exception as e:
            logger.warning(f"Could not initialize LIME LimeTabularExplainer: {e}")
            self.lime_explainer = None

    def explain_shap(
        self,
        features: dict[str, float],
        feature_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Genuine SHAP TreeExplainer attribution.
        Maps exact feature names, handles binary classification output shapes,
        and provides clear non-causal warnings.
        """
        if self.shap_explainer is None or self.model is None:
            raise RuntimeError("SHAP TreeExplainer is unavailable or active model is not loaded.")

        names = feature_names or self.feature_names
        vec = np.array([[float(features.get(name, 0.0)) for name in names]], dtype=np.float64)
        shap_values = self.shap_explainer.shap_values(vec)

        # Handle differing SHAP return shapes:
        # 1. 3D array (n_samples, n_features, n_classes) -> take class 1 (failure risk)
        # 2. List of arrays [class0_arr, class1_arr]
        # 3. 2D array (n_samples, n_features)
        # 4. 1D array (n_features)
        if isinstance(shap_values, list):
            values = shap_values[1][0] if len(shap_values) > 1 else shap_values[0][0]
        elif isinstance(shap_values, np.ndarray):
            if shap_values.ndim == 3:
                values = shap_values[0, :, 1] if shap_values.shape[2] > 1 else shap_values[0, :, 0]
            elif shap_values.ndim == 2:
                values = shap_values[0]
            else:
                values = shap_values
        else:
            raise ValueError(f"Unexpected SHAP values type: {type(shap_values)}")

        feature_impacts: list[dict[str, Any]] = []
        for name, val in zip(names, values):
            score = round(float(val), 4)
            feature_impacts.append({
                "feature": name,
                "observed_value": float(features.get(name, 0.0)),
                "attribution_score": score,
                "direction": "increases_risk" if score > 0 else "decreases_risk",
            })

        feature_impacts.sort(key=lambda x: abs(x["attribution_score"]), reverse=True)

        return {
            "method": "shap_tree_attribution",
            "is_fallback": False,
            "top_contributing_features": feature_impacts[:5],
            "all_features": feature_impacts,
            "interpretation_note": (
                "SHAP values indicate additive feature attribution to model score, "
                "not causal mechanics or direct failure drivers."
            ),
        }

    def explain_lime(
        self,
        features: dict[str, float],
        feature_names: list[str] | None = None,
        num_features: int = 5,
    ) -> dict[str, Any]:
        """
        Genuine LIME LimeTabularExplainer local surrogate explanation.
        Explains instance using local linear approximation around observation.
        """
        if self.lime_explainer is None or self.model is None or not hasattr(self.model, "predict_proba"):
            raise RuntimeError("LIME TabularExplainer is unavailable or model lacks predict_proba.")

        names = feature_names or self.feature_names
        vec_1d = np.array([float(features.get(name, 0.0)) for name in names], dtype=np.float64)

        exp = self.lime_explainer.explain_instance(
            vec_1d,
            self.model.predict_proba,
            num_features=min(num_features, len(names)),
            labels=(1,),
        )

        local_exp = exp.local_exp.get(1, [])
        rule_tuples = dict(exp.as_list(label=1))

        feature_impacts: list[dict[str, Any]] = []
        for idx, weight in local_exp:
            idx_int = int(idx)
            feat_name = names[idx_int] if idx_int < len(names) else f"feature_{idx_int}"
            score = round(float(weight), 4)
            # Find rule condition if available
            condition = next((r for r, w in rule_tuples.items() if feat_name in r), f"{feat_name} local effect")
            feature_impacts.append({
                "feature": feat_name,
                "condition": condition,
                "observed_value": float(features.get(feat_name, 0.0)),
                "attribution_score": score,
                "direction": "increases_risk" if score > 0 else "decreases_risk",
            })

        feature_impacts.sort(key=lambda x: abs(x["attribution_score"]), reverse=True)

        return {
            "method": "lime_tabular_surrogate",
            "is_fallback": False,
            "top_contributing_features": feature_impacts[:5],
            "all_features": feature_impacts,
            "interpretation_note": (
                "LIME local surrogate linear approximation. "
                "Indicates local feature association with risk score, not causal mechanics."
            ),
        }

    def explain_heuristic(
        self,
        features: dict[str, float],
        feature_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Normalized feature deviation heuristic fallback.
        Explicitly marked with is_fallback=True.
        """
        healthy_baselines = {
            "avg_latency_ms": 200.0,
            "p95_latency_ms": 400.0,
            "latency_trend": 1.0,
            "error_rate": 0.0,
            "timeout_rate": 0.0,
            "http_4xx_rate": 0.0,
            "http_5xx_rate": 0.0,
            "availability": 100.0,
            "recent_consecutive_failures": 0.0,
        }

        weights = {
            "recent_consecutive_failures": 3.0,
            "http_5xx_rate": 2.5,
            "error_rate": 2.0,
            "timeout_rate": 2.0,
            "availability": 1.8,
            "latency_trend": 1.5,
            "p95_latency_ms": 1.0,
            "avg_latency_ms": 0.8,
        }

        feature_impacts: list[dict[str, Any]] = []

        for feat, weight in weights.items():
            obs_val = float(features.get(feat, 0.0))
            baseline_val = healthy_baselines.get(feat, 0.0)

            if feat == "availability":
                delta = max(0.0, baseline_val - obs_val)
                score = (delta / 100.0) * weight
            elif feat == "latency_trend":
                delta = max(0.0, obs_val - 1.0)
                score = delta * weight
            elif "latency" in feat:
                delta = max(0.0, obs_val - baseline_val)
                score = (delta / 1000.0) * weight
            else:
                delta = max(0.0, obs_val - baseline_val)
                score = (delta / 10.0) * weight

            if score > 0.01:
                feature_impacts.append({
                    "feature": feat,
                    "observed_value": obs_val,
                    "attribution_score": round(score, 3),
                    "direction": "increases_risk",
                })

        feature_impacts.sort(key=lambda x: x["attribution_score"], reverse=True)

        return {
            "method": "normalized_feature_attribution",
            "is_fallback": True,
            "top_contributing_features": feature_impacts[:5],
            "all_features": feature_impacts,
            "interpretation_note": (
                "Relative feature contribution to estimated failure risk based on deviations "
                "from normal baseline (heuristic fallback)."
            ),
        }

    def explain(
        self,
        features: dict[str, float],
        risk_score: float,
        provenance: str,
        feature_names: list[str] | None = None,
        method: str = "shap",
    ) -> dict[str, Any]:
        """
        Explains prediction using the selected explainability method: 'shap', 'lime', or 'heuristic'.
        If genuine SHAP or LIME fails or is unavailable, transparently falls back to heuristic attribution
        with is_fallback=True.
        """
        names = feature_names or self.feature_names

        # If rules baseline provenance or explicitly requested heuristic
        if provenance == "rules_baseline" or method == "heuristic":
            return self.explain_heuristic(features, names)

        # Try SHAP
        if method == "shap":
            if self.shap_explainer is not None:
                try:
                    return self.explain_shap(features, names)
                except Exception as e:
                    logger.warning(f"SHAP explanation failed, falling back to heuristic: {e}")
            elif self.lime_explainer is not None:
                try:
                    return self.explain_lime(features, names)
                except Exception as e:
                    logger.warning(f"LIME fallback failed: {e}")

        # Try LIME
        elif method == "lime":
            if self.lime_explainer is not None:
                try:
                    return self.explain_lime(features, names)
                except Exception as e:
                    logger.warning(f"LIME explanation failed, falling back to heuristic: {e}")
            elif self.shap_explainer is not None:
                try:
                    return self.explain_shap(features, names)
                except Exception as e:
                    logger.warning(f"SHAP fallback failed: {e}")

        # Fallback to heuristic
        return self.explain_heuristic(features, names)
