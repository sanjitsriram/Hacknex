"""API schemas for evaluation runs and benchmark metrics."""

from typing import List, Optional
from pydantic import BaseModel, Field


class EvaluationItemResponse(BaseModel):
    """Benchmark run item with verifiable hash and denominator."""

    id: str = Field(description="Run ID")
    dataset: str = Field(description="Dataset name")
    subset: str = Field(description="Subset/split name")
    metric: str = Field(description="Metric name, e.g. 'CER', 'WER'")
    score: float = Field(description="Score value")
    denominator: int = Field(description="Sample or character count")
    dataset_hash: str = Field(description="SHA-256 hash of dataset")
    model_version: str = Field(description="Model/pipeline version tag")
    timestamp: str = Field(description="Execution timestamp")
    is_demo: bool = Field(default=False, description="Whether synthetic sample")


class EvaluationResponse(BaseModel):
    """List of benchmark evaluation runs."""

    runs: List[EvaluationItemResponse] = Field(description="Evaluation records")
    total: int = Field(ge=0, description="Total evaluation records")
