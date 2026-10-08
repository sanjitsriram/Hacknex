"""Unit tests for TextHypothesisAligner (ROVER-inspired word/char alignment)."""

import pytest
from evidence_ocr.fusion.text_aligner import TextHypothesisAligner, _is_critical_token, _normalize, _tokenize
from evidence_ocr.models.fusion import AgreementLevel


def make_candidate(text, source="trocr", version="base-v1", conf=0.9):
    aligner = TextHypothesisAligner()
    return aligner.build_hypothesis_candidate(source, version, text, conf)


def test_normalize_lowercase_strips():
    assert _normalize("  Hello   World  ") == "hello world"


def test_tokenize_splits_on_whitespace():
    assert _tokenize("The cat sat") == ["the", "cat", "sat"]


def test_tokenize_empty():
    assert _tokenize("") == []


def test_is_critical_numeric():
    assert _is_critical_token("4.8") is True
    assert _is_critical_token("39") is True


def test_is_critical_date():
    assert _is_critical_token("12/10/2026") is True


def test_is_critical_unit():
    assert _is_critical_token("4.8m") is True
    assert _is_critical_token("50kg") is True


def test_is_critical_non_critical():
    assert _is_critical_token("the") is False
    assert _is_critical_token("wall") is False


def test_build_hypothesis_candidate():
    aligner = TextHypothesisAligner()
    c = aligner.build_hypothesis_candidate("trocr", "v1", "Hello World", 0.9)
    assert c.raw_text == "Hello World"
    assert c.normalized_text == "hello world"
    assert c.word_tokens == ["hello", "world"]
    assert c.source_model == "trocr"


def test_align_single_candidate_single_model_only():
    aligner = TextHypothesisAligner()
    c = make_candidate("The north wall")
    result = aligner.align("r1", [c])
    assert result.overall_agreement == AgreementLevel.SINGLE_MODEL_ONLY
    assert len(result.positions) == 3  # "the", "north", "wall"


def test_align_two_candidates_full_agreement():
    aligner = TextHypothesisAligner()
    c1 = make_candidate("The north wall", source="trocr")
    c2 = make_candidate("The north wall", source="paddleocr-cloud")
    result = aligner.align("r1", [c1, c2])
    assert result.overall_agreement == AgreementLevel.FULL_AGREEMENT
    for pos in result.positions:
        assert pos.agreement == AgreementLevel.FULL_AGREEMENT


def test_align_numeric_conflict_detected():
    aligner = TextHypothesisAligner()
    c1 = make_candidate("measures 4.8 metres", source="trocr")
    c2 = make_candidate("measures 4.3 metres", source="paddleocr-cloud")
    result = aligner.align("r1", [c1, c2])
    # Should have at least one SUBSTITUTION position
    disagreed = [p for p in result.positions if p.agreement != AgreementLevel.FULL_AGREEMENT]
    assert len(disagreed) >= 1
    # The conflicting position should be flagged as critical (4.8 vs 4.3 are numeric)
    numeric_positions = [p for p in disagreed if p.is_critical]
    assert len(numeric_positions) >= 1


def test_align_raw_text_preserved():
    aligner = TextHypothesisAligner()
    raw_a = "The WALL measures 4.8m"
    raw_b = "THE wall measures 4.3m"
    c1 = make_candidate(raw_a, source="trocr")
    c2 = make_candidate(raw_b, source="paddleocr-cloud")
    result = aligner.align("r1", [c1, c2])
    # Raw text must be preserved in candidates
    assert result.candidates[0].raw_text == raw_a
    assert result.candidates[1].raw_text == raw_b


def test_align_three_candidates_minority_disagreement():
    aligner = TextHypothesisAligner()
    c1 = make_candidate("The bracket below", source="trocr")
    c2 = make_candidate("The bracket below", source="paddleocr-cloud")
    c3 = make_candidate("The basket below", source="paddleocr-vl-cloud")
    result = aligner.align("r1", [c1, c2, c3])
    # Two agree on "bracket", one disagrees with "basket"
    minority_positions = [p for p in result.positions
                          if p.agreement == AgreementLevel.MINORITY_DISAGREEMENT]
    assert len(minority_positions) >= 1


def test_align_empty_candidates():
    aligner = TextHypothesisAligner()
    result = aligner.align("r1", [])
    assert result.overall_agreement == AgreementLevel.SINGLE_MODEL_ONLY
    assert result.positions == []


def test_align_pairwise_ops_populated():
    aligner = TextHypothesisAligner()
    c1 = make_candidate("hello world", source="trocr")
    c2 = make_candidate("hello earth", source="paddleocr-cloud")
    result = aligner.align("r1", [c1, c2])
    assert "trocr_vs_paddleocr-cloud" in result.pairwise_ops
    ops = result.pairwise_ops["trocr_vs_paddleocr-cloud"]
    assert len(ops) > 0


def test_align_unicode_text():
    aligner = TextHypothesisAligner()
    c1 = make_candidate("Bella Bella Marie", source="trocr")
    c2 = make_candidate("Delia Delia Marie", source="paddleocr-cloud")
    result = aligner.align("r1", [c1, c2])
    disagreed = [p for p in result.positions if p.agreement != AgreementLevel.FULL_AGREEMENT]
    assert len(disagreed) >= 1


def test_align_insertion_detected():
    aligner = TextHypothesisAligner()
    c1 = make_candidate("hello world", source="trocr")
    c2 = make_candidate("hello brave new world", source="paddleocr-cloud")
    result = aligner.align("r1", [c1, c2])
    assert result.overall_agreement != AgreementLevel.FULL_AGREEMENT
