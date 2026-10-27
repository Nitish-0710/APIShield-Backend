from enum import Enum
from typing import Optional


class PredictionProvenance(str, Enum):
    TRAINED_MODEL = "trained_model"
    RULES_BASELINE = "rules_baseline"
    DEMO = "demo"


def resolve_prediction_provenance(
    has_active_trained_model: bool,
    is_demo_mode: bool = False,
    is_model_stale: bool = False,
) -> str:
    """
    Explicitly resolves prediction provenance.
    Never silently substitutes demo or heuristic predictions for a trained model.
    """
    if is_demo_mode:
        return PredictionProvenance.DEMO.value

    if has_active_trained_model and not is_model_stale:
        return PredictionProvenance.TRAINED_MODEL.value

    return PredictionProvenance.RULES_BASELINE.value
