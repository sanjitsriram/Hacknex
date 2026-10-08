"""Domain models for benchmark evaluations and accuracy tracking."""

from typing import Optional
from pydantic import BaseModel, Field


class EvaluationRun(BaseModel):
    """Benchmark evaluation run entity with verifiable hashes and sample denominators."""

    id: str = Field(description="Unique evaluation run identifier")
    dataset: str = Field(description="Evaluation dataset name, e.g. 'IAM-Handwriting' or 'SiteNotes-Benchmark'")
    subset: str = Field(default="test", description="Subset or split: 'train', 'val', 'test'")
    metric: str = Field(description="Accuracy metric name, e.g. 'CER', 'WER', 'CharacterAccuracy'")
    score: float = Field(ge=0.0, le=100.0, description="Metric score percentage or value")
    denominator: int = Field(gt=0, description="Exact number of evaluated characters or tokens")
    dataset_hash: str = Field(description="SHA-256 hash of dataset split for reproducibility")
    model_version: str = Field(description="Cloud model version or fusion ensemble tag")
    timestamp: str = Field(description="UTC ISO-8601 evaluation execution timestamp")
    is_demo: bool = Field(default=False, description="Flag explicitly designating synthetic demonstration runs")
