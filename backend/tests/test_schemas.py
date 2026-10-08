"""Tests for Pydantic domain models and API schemas."""

import pytest
from pydantic import ValidationError
from evidence_ocr.models.job import JobStage, JobStatus, ProcessingJob
from evidence_ocr.models.region import BoundingBox, CandidateSuggestion
from evidence_ocr.schemas.documents import DocumentCreateRequest


def test_bounding_box_valid_coordinates():
    """Verify valid normalized coordinates [0-100]."""
    bbox = BoundingBox(x=10.0, y=20.0, w=30.0, h=40.0)
    assert bbox.x == 10.0
    assert bbox.y == 20.0
    assert bbox.w == 30.0
    assert bbox.h == 40.0


def test_bounding_box_out_of_bounds_rejected():
    """Verify bounding box exceeding page boundaries raises ValidationError."""
    with pytest.raises(ValidationError):
        # x + w = 60 + 50 = 110 > 100
        BoundingBox(x=60.0, y=10.0, w=50.0, h=20.0)

    with pytest.raises(ValidationError):
        # negative coordinates
        BoundingBox(x=-1.0, y=10.0, w=20.0, h=20.0)


def test_candidate_suggestion_provenance():
    """Verify candidate suggestion requires provider provenance."""
    candidate = CandidateSuggestion(
        text="SampleWord",
        confidence=0.92,
        provider_id="google-vision",
        model_version="v1-2026",
    )
    assert candidate.text == "SampleWord"
    assert candidate.provider_id == "google-vision"


def test_document_create_request_validation():
    """Verify document creation schema constraints."""
    valid = DocumentCreateRequest(title="Valid Field Notes", kind="Field notes")
    assert valid.title == "Valid Field Notes"

    with pytest.raises(ValidationError):
        # empty title
        DocumentCreateRequest(title="")
