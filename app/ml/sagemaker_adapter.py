import os
from typing import Any, Dict, List, Optional


class SageMakerAdapter:
    """
    AWS SageMaker integration adapter stub.
    Provides contract definitions and future integration boundaries for
    cloud-based model training and real-time endpoint inference on AWS.

    NOTE: This is an architectural adapter boundary. It operates in offline/mock
    mode when AWS credentials or boto3 are not configured, preserving 100% local operation.
    """

    def __init__(
        self,
        role_arn: str | None = None,
        s3_bucket: str | None = None,
        endpoint_name: str | None = None,
    ):
        self.role_arn = role_arn or os.getenv("SAGEMAKER_ROLE_ARN")
        self.s3_bucket = s3_bucket or os.getenv("SAGEMAKER_S3_BUCKET")
        self.endpoint_name = endpoint_name or os.getenv("SAGEMAKER_ENDPOINT_NAME")
        self.is_configured = bool(self.role_arn and self.s3_bucket)

    def trigger_training_job(
        self,
        training_data_s3_uri: str,
        hyperparameters: dict[str, Any],
        job_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Dispatches a remote training job to AWS SageMaker.
        Returns job status or offline simulation status.
        """
        if not self.is_configured:
            return {
                "status": "unconfigured_local_fallback",
                "message": (
                    "SageMaker integration is not configured. Set SAGEMAKER_ROLE_ARN "
                    "and SAGEMAKER_S3_BUCKET to enable AWS cloud training."
                ),
                "is_remote_execution": False,
            }

        # Future Boto3 SageMaker dispatch boundary
        return {
            "status": "ready_for_dispatch",
            "role_arn": self.role_arn,
            "s3_bucket": self.s3_bucket,
            "training_uri": training_data_s3_uri,
            "is_remote_execution": True,
        }

    def invoke_remote_endpoint(
        self,
        features: list[float],
    ) -> dict[str, Any]:
        """
        Invokes an active AWS SageMaker real-time endpoint.
        Returns endpoint prediction or offline fallback notice.
        """
        if not self.endpoint_name:
            return {
                "status": "offline_stub",
                "message": "SageMaker endpoint name not configured. Using local inference engine.",
                "is_remote_inference": False,
            }

        return {
            "status": "endpoint_dispatch_stub",
            "endpoint_name": self.endpoint_name,
            "is_remote_inference": True,
        }
