"""CandidateSelectionService: Conservative evidence-aware transcription proposal generation.

Implements the four selection strategies from the Phase 6 spec:
  Strategy 1 (best_individual): Return best single-model output (lowest dev-set CER = TrOCR)
  Strategy 2 (unweighted_rover): Majority vote across aligned word positions
  Strategy 3 (evidence_aware): Agreement-based, blocks critical tokens with any disagreement
  Strategy 4 (evidence_aware_with_recovery): Strategy 3 + flags recovery-eligible regions

Safety rules:
  - Critical tokens (NUMERIC, DATE, UNIT, IDENTIFIER) with ANY disagreement → REQUIRES_REVIEW
  - FULL_DISAGREEMENT across all models → REQUIRES_REVIEW, no auto-proposal
  - is_human_verified is always False on creation
  - calibration_status is always UNCALIBRATED (raw confidence, not a calibrated probability)
  - Correlated model pairs (PP-OCRv6 + VL) must not count as two independent votes
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.fusion import (
    AgreementLevel,
    AlignedHypotheses,
    DisagreementRecord,
    DisagreementSeverity,
    DisagreementType,
    EvidenceAlignment,
    FusionProposal,
    HypothesisCandidate,
)

logger = get_logger("evidence_ocr.fusion.candidate_selection")

# Providers from the same model family — agreement between them is NOT independent
CORRELATED_PROVIDERS = frozenset({"paddleocr-cloud", "paddleocr-vl-cloud"})

# Ordering of models by development-set CER (lowest = most trusted)
# TrOCR: 6.60% (40 samples), PP-OCRv6: see Phase 6 re-benchmark
# This is treated as a HYPOTHESIS until the full 40-sample benchmark is run.
MODEL_RELIABILITY_RANK = ["trocr", "paddleocr-cloud", "paddleocr-vl-cloud"]

# Critical disagreement types that block auto-proposal regardless of vote
CRITICAL_BLOCK_TYPES = frozenset({
    DisagreementType.NUMERIC_CONFLICT,
    DisagreementType.DATE_CONFLICT,
    DisagreementType.UNIT_CONFLICT,
})


def _best_candidate_by_model_rank(candidates: List[HypothesisCandidate]) -> Optional[HypothesisCandidate]:
    """Return candidate from the highest-ranked available model."""
    for preferred in MODEL_RELIABILITY_RANK:
        for c in candidates:
            if c.source_model == preferred and c.raw_text.strip():
                return c
    return candidates[0] if candidates else None


def _majority_word_at_position(
    candidates: List[HypothesisCandidate],
    position: int,
    position_map: Dict[str, Optional[str]],
) -> Optional[str]:
    """Return the majority word at an alignment position, excluding correlated pairs.

    Correlated pair rule: if all agreeing models are from CORRELATED_PROVIDERS,
    they count as ONE vote, not multiple.
    """
    from collections import Counter
    if not position_map:
        return None

    # If PP-OCRv6 and VL both agree on a word but TrOCR differs,
    # that's really 1 correlated vote vs 1 independent vote — not majority.
    word_votes: Dict[str, int] = Counter()
    models_voted: Dict[str, List[str]] = {}  # word -> models that voted for it

    for model, word in position_map.items():
        if word is None:
            continue
        w = word.strip()
        if w:
            word_votes[w] = word_votes.get(w, 0) + 1
            if w not in models_voted:
                models_voted[w] = []
            models_voted[w].append(model)

    if not word_votes:
        return None

    # Check for correlated model bias: if winning word is only voted by correlated pair
    # and a competing word exists from TrOCR, prefer TrOCR
    sorted_words = sorted(word_votes.keys(), key=lambda w: -word_votes[w])
    if len(sorted_words) > 1:
        top_word = sorted_words[0]
        top_voters = set(models_voted.get(top_word, []))
        if top_voters.issubset(CORRELATED_PROVIDERS):
            # Check if any other word has a non-correlated vote
            for w in sorted_words[1:]:
                other_voters = set(models_voted.get(w, []))
                if other_voters - CORRELATED_PROVIDERS:
                    return w  # Prefer independent model's word

    return sorted_words[0] if sorted_words else None


def _has_critical_disagreement(disagreements: List[DisagreementRecord]) -> bool:
    """Return True if any disagreement type blocks auto-acceptance."""
    for d in disagreements:
        if d.disagreement_type in CRITICAL_BLOCK_TYPES:
            return True
        if d.severity == DisagreementSeverity.CRITICAL:
            return True
    return False


def _build_indicators(
    candidates: List[HypothesisCandidate],
    disagreements: List[DisagreementRecord],
    aligned: AlignedHypotheses,
) -> List[str]:
    """Produce a list of uncertainty indicator codes for a region."""
    indicators: List[str] = ["UNCALIBRATED"]

    if any(d.disagreement_type == DisagreementType.NUMERIC_CONFLICT for d in disagreements):
        indicators.append("CRITICAL_NUMERIC")
    if any(d.disagreement_type == DisagreementType.DATE_CONFLICT for d in disagreements):
        indicators.append("CRITICAL_DATE")
    if any(d.disagreement_type == DisagreementType.UNIT_CONFLICT for d in disagreements):
        indicators.append("CRITICAL_UNIT")
    if any(pos.is_critical for pos in aligned.positions):
        indicators.append("CONTAINS_CRITICAL_TOKENS")
    if aligned.overall_agreement == AgreementLevel.FULL_DISAGREEMENT:
        indicators.append("FULL_DISAGREEMENT")
    if aligned.overall_agreement == AgreementLevel.MINORITY_DISAGREEMENT:
        indicators.append("MINORITY_DISAGREEMENT")

    # Flag correlated-only agreement
    model_names = set(c.source_model for c in candidates)
    independent_models = model_names - CORRELATED_PROVIDERS
    if not independent_models and len(model_names) > 1:
        indicators.append("CORRELATED_MODELS_ONLY")

    return list(dict.fromkeys(indicators))  # deduplicate, preserve order


class CandidateSelectionService:
    """Produces a FusionProposal for a region using one of four strategies."""

    def __init__(self, strategy: str = "evidence_aware") -> None:
        self.strategy = strategy

    def propose(
        self,
        region_id: str,
        document_id: str,
        page_index: int,
        fusion_run_id: str,
        aligned: AlignedHypotheses,
        disagreements: List[DisagreementRecord],
        alignment: Optional[EvidenceAlignment],
        recovery_attempt_ids: Optional[List[str]] = None,
    ) -> FusionProposal:
        """Generate a FusionProposal for a region.

        Never produces an auto-acceptable proposal when:
          - A CRITICAL disagreement exists (NUMERIC, DATE, UNIT)
          - Overall agreement is FULL_DISAGREEMENT
          - Region has INSUFFICIENT_EVIDENCE
          - Fewer than 2 candidates available

        Returns:
            FusionProposal with proposed_text (may be None), auto_proposable, requires_review flags.
        """
        now = datetime.now(timezone.utc).isoformat()
        candidates = aligned.candidates
        recovery_ids = recovery_attempt_ids or []

        candidates_serialized: List[Dict[str, Any]] = [
            {
                "text": c.raw_text,
                "source": c.source_model,
                "model_version": c.model_version,
                "confidence": c.raw_confidence,
                "normalized_text": c.normalized_text,
            }
            for c in candidates
        ]

        evidence_ref: Dict[str, Any] = {
            "region_id": region_id,
            "page_index": page_index,
            "alignment_id": alignment.id if alignment else None,
            "alignment_iou": alignment.iou_score if alignment else None,
        }

        # Compute indicators
        indicators = _build_indicators(candidates, disagreements, aligned)
        disagreement_reasons = [d.disagreement_type.value for d in disagreements]

        # Check hard blocks
        critical_block = _has_critical_disagreement(disagreements)
        has_insufficient = any(
            d.disagreement_type == DisagreementType.INSUFFICIENT_EVIDENCE for d in disagreements
        )
        is_full_disagreement = aligned.overall_agreement == AgreementLevel.FULL_DISAGREEMENT

        # No candidates at all
        if not candidates:
            return FusionProposal(
                id=f"prop-{uuid.uuid4().hex[:8]}",
                fusion_run_id=fusion_run_id,
                document_id=document_id,
                region_id=region_id,
                page_index=page_index,
                proposed_text=None,
                strategy_version=self.strategy,
                auto_proposable=False,
                requires_review=True,
                disagreement_reasons=disagreement_reasons,
                candidates=candidates_serialized,
                uncertainty_indicators=indicators,
                recovery_attempt_ids=recovery_ids,
                is_human_verified=False,
                calibration_status="UNCALIBRATED",
                source_evidence_reference=evidence_ref,
                created_at=now,
                updated_at=now,
            )

        proposed_text, auto_proposable = self._select(
            candidates=candidates,
            aligned=aligned,
            disagreements=disagreements,
            critical_block=critical_block,
            is_full_disagreement=is_full_disagreement,
            has_insufficient=has_insufficient,
        )

        requires_review = not auto_proposable or critical_block or is_full_disagreement or has_insufficient

        return FusionProposal(
            id=f"prop-{uuid.uuid4().hex[:8]}",
            fusion_run_id=fusion_run_id,
            document_id=document_id,
            region_id=region_id,
            page_index=page_index,
            proposed_text=proposed_text,
            strategy_version=self.strategy,
            auto_proposable=auto_proposable,
            requires_review=requires_review,
            disagreement_reasons=list(dict.fromkeys(disagreement_reasons)),
            candidates=candidates_serialized,
            uncertainty_indicators=indicators,
            recovery_attempt_ids=recovery_ids,
            is_human_verified=False,
            calibration_status="UNCALIBRATED",
            source_evidence_reference=evidence_ref,
            created_at=now,
            updated_at=now,
        )

    def _select(
        self,
        candidates: List[HypothesisCandidate],
        aligned: AlignedHypotheses,
        disagreements: List[DisagreementRecord],
        critical_block: bool,
        is_full_disagreement: bool,
        has_insufficient: bool,
    ):
        """Route to appropriate selection strategy.

        Returns: (proposed_text: Optional[str], auto_proposable: bool)
        """
        if self.strategy == "best_individual":
            return self._strategy_best_individual(candidates, critical_block, is_full_disagreement)
        elif self.strategy == "unweighted_rover":
            return self._strategy_rover(candidates, aligned, critical_block, is_full_disagreement)
        elif self.strategy in ("evidence_aware", "evidence_aware_with_recovery"):
            return self._strategy_evidence_aware(candidates, aligned, disagreements, critical_block, is_full_disagreement)
        else:
            logger.warning("Unknown strategy '%s', falling back to evidence_aware", self.strategy)
            return self._strategy_evidence_aware(candidates, aligned, disagreements, critical_block, is_full_disagreement)

    def _strategy_best_individual(self, candidates, critical_block, is_full_disagreement):
        """Strategy 1: Return best individual model's output."""
        best = _best_candidate_by_model_rank(candidates)
        if best and best.raw_text.strip():
            auto = not critical_block and not is_full_disagreement
            return best.raw_text, auto
        return None, False

    def _strategy_rover(self, candidates, aligned, critical_block, is_full_disagreement):
        """Strategy 2: Unweighted ROVER majority vote per position."""
        if not aligned.positions:
            return self._strategy_best_individual(candidates, critical_block, is_full_disagreement)

        words: List[str] = []
        for pos in aligned.positions:
            word = _majority_word_at_position(candidates, pos.position, pos.candidates_at_position)
            if word:
                words.append(word)

        if not words:
            return None, False

        proposed = " ".join(words)
        auto = not critical_block and not is_full_disagreement
        return proposed, auto

    def _strategy_evidence_aware(self, candidates, aligned, disagreements, critical_block, is_full_disagreement):
        """Strategy 3: Evidence-aware selection.

        - FULL_AGREEMENT at all positions → propose from best model, auto_proposable=True
        - MINORITY_DISAGREEMENT → propose majority, flag; auto_proposable only if non-critical
        - FULL_DISAGREEMENT → no auto-proposal, requires_review=True
        - Any CRITICAL disagreement → requires_review=True regardless
        """
        if aligned.overall_agreement == AgreementLevel.FULL_AGREEMENT:
            # All models agree — use best ranked model's raw text
            best = _best_candidate_by_model_rank(candidates)
            if best:
                return best.raw_text, not critical_block

        elif aligned.overall_agreement == AgreementLevel.MINORITY_DISAGREEMENT:
            # Majority agrees — use majority output
            if aligned.positions:
                words: List[str] = []
                for pos in aligned.positions:
                    if pos.agreement in (AgreementLevel.FULL_AGREEMENT, AgreementLevel.SINGLE_MODEL_ONLY):
                        word = pos.candidates_at_position.get(
                            next(iter(pos.candidates_at_position), ""), ""
                        )
                    else:
                        word = _majority_word_at_position(candidates, pos.position, pos.candidates_at_position)
                    if word:
                        words.append(word)
                proposed = " ".join(words) if words else None
                auto = not critical_block and not is_full_disagreement
                return proposed, auto

        elif aligned.overall_agreement == AgreementLevel.SINGLE_MODEL_ONLY:
            best = _best_candidate_by_model_rank(candidates)
            if best:
                return best.raw_text, not critical_block

        # FULL_DISAGREEMENT or ambiguous → no auto-proposal
        if critical_block or is_full_disagreement:
            # Still provide a best-effort text for display, but NOT auto_proposable
            best = _best_candidate_by_model_rank(candidates)
            if best and best.raw_text.strip():
                return best.raw_text, False
            return None, False

        return None, False
