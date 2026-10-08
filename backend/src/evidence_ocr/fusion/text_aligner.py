"""TextHypothesisAligner: ROVER-inspired word and character-level alignment of OCR hypothesis sequences.

Algorithm:
1. Normalize each candidate for alignment (lowercase, collapse whitespace) - normalization
   is NEVER applied to the stored raw_text - only used for computing edit operations.
2. For each pair of candidates, compute word-level Levenshtein edit operations.
3. Merge pairwise alignment ops into a multi-model position lattice.
4. At each position: classify agreement level (FULL_AGREEMENT, MINORITY_DISAGREEMENT, etc.)
5. For SUBSTITUTION positions: run character-level edit ops to find exact conflict chars.
6. Flag positions containing critical tokens (numbers, dates, units, identifiers).

References:
- ROVER: Fisher et al., NIST 1997
- Levenshtein: V.I. Levenshtein, 1966
- rapidfuzz: https://github.com/maxbachmann/RapidFuzz
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.fusion import (
    AgreementLevel,
    AlignedHypotheses,
    AlignedPosition,
    AlignOpType,
    HypothesisCandidate,
)

logger = get_logger("evidence_ocr.fusion.text_aligner")

# Patterns for critical token detection
_NUMERIC_RE = re.compile(r"\b\d+[\d.,/-]*\b")
_DATE_RE = re.compile(
    r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})\b"
)
_UNIT_RE = re.compile(
    r"\b(\d+[\s]?)(mm|cm|m|km|mg|g|kg|ml|l|lb|oz|ft|in|psi|kpa|bar|deg|pc|%)\b",
    re.IGNORECASE,
)
_IDENTIFIER_RE = re.compile(r"\b([A-Z]{2,}\d+|\d+[A-Z]{2,})\b")


def _normalize(text: str) -> str:
    """Deterministic alignment normalization: lowercase + collapse whitespace.

    NEVER modify original model output. This is used only for computing
    alignment edit operations.
    """
    return re.sub(r"\s+", " ", text.lower().strip())


def _tokenize(text: str) -> List[str]:
    """Whitespace tokenization on normalized text."""
    normalized = _normalize(text)
    return normalized.split() if normalized else []


def _is_critical_token(word: str) -> bool:
    """Return True if a word contains a numeric, date, unit, or identifier pattern."""
    if not word:
        return False
    if _NUMERIC_RE.search(word):
        return True
    if _DATE_RE.search(word):
        return True
    if _UNIT_RE.search(word):
        return True
    if _IDENTIFIER_RE.search(word):
        return True
    return False


def _word_editops(seq_a: List[str], seq_b: List[str]) -> List[Dict[str, Any]]:
    """Compute word-level edit operations between two tokenized sequences.

    Returns list of dicts with keys: op_type, src_word, dst_word, src_pos, dst_pos.
    Uses rapidfuzz.distance.Levenshtein.editops for efficiency.
    Falls back to pure-Python DP backtrace if rapidfuzz unavailable.
    """
    try:
        from rapidfuzz.distance import Levenshtein as RFL
        raw_ops = RFL.editops(seq_a, seq_b)
        result: List[Dict[str, Any]] = []
        # Build MATCH positions first by filling gaps between edit ops
        # rapidfuzz editops only lists non-match ops
        ops_by_src: Dict[int, Dict] = {}
        ops_by_dst: Dict[int, Dict] = {}
        for op in raw_ops:
            tag, src_pos, dst_pos = op
            entry: Dict[str, Any] = {"op_type": None, "src_word": None, "dst_word": None,
                                      "src_pos": src_pos, "dst_pos": dst_pos}
            if tag == "replace":
                entry["op_type"] = AlignOpType.SUBSTITUTION
                entry["src_word"] = seq_a[src_pos] if src_pos < len(seq_a) else None
                entry["dst_word"] = seq_b[dst_pos] if dst_pos < len(seq_b) else None
            elif tag == "insert":
                entry["op_type"] = AlignOpType.INSERTION
                entry["dst_word"] = seq_b[dst_pos] if dst_pos < len(seq_b) else None
            elif tag == "delete":
                entry["op_type"] = AlignOpType.DELETION
                entry["src_word"] = seq_a[src_pos] if src_pos < len(seq_a) else None
            result.append(entry)

        # Add MATCH records for all unedited positions
        edited_src = {op["src_pos"] for op in result if op.get("src_pos") is not None
                      and op["op_type"] != AlignOpType.INSERTION}
        for i, word in enumerate(seq_a):
            if i not in edited_src:
                result.append({"op_type": AlignOpType.MATCH, "src_word": word,
                                "dst_word": None, "src_pos": i, "dst_pos": None})
        return result

    except ImportError:
        logger.warning("rapidfuzz not available; using pure-Python DP backtrace")
        return _word_editops_pure(seq_a, seq_b)


def _word_editops_pure(seq_a: List[str], seq_b: List[str]) -> List[Dict[str, Any]]:
    """Pure-Python word-level edit operations via DP backtrace."""
    n, m = len(seq_a), len(seq_b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1])

    # Backtrace
    ops: List[Dict[str, Any]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and seq_a[i - 1] == seq_b[j - 1]:
            ops.append({"op_type": AlignOpType.MATCH, "src_word": seq_a[i - 1],
                        "dst_word": seq_b[j - 1], "src_pos": i - 1, "dst_pos": j - 1})
            i -= 1; j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            ops.append({"op_type": AlignOpType.SUBSTITUTION, "src_word": seq_a[i - 1],
                        "dst_word": seq_b[j - 1], "src_pos": i - 1, "dst_pos": j - 1})
            i -= 1; j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append({"op_type": AlignOpType.DELETION, "src_word": seq_a[i - 1],
                        "dst_word": None, "src_pos": i - 1, "dst_pos": None})
            i -= 1
        else:
            ops.append({"op_type": AlignOpType.INSERTION, "src_word": None,
                        "dst_word": seq_b[j - 1], "src_pos": None, "dst_pos": j - 1})
            j -= 1

    ops.reverse()
    return ops


def _char_editops(word_a: str, word_b: str) -> List[Dict[str, Any]]:
    """Character-level edit operations within a substituted word pair.

    Returns a list of character-level {op, char_a, char_b, pos_a, pos_b} dicts.
    """
    try:
        from rapidfuzz.distance import Levenshtein as RFL
        raw_ops = RFL.editops(list(word_a), list(word_b))
        result = []
        for op in raw_ops:
            tag, src, dst = op
            entry = {
                "op": tag,
                "char_a": word_a[src] if tag in ("replace", "delete") and src < len(word_a) else None,
                "char_b": word_b[dst] if tag in ("replace", "insert") and dst < len(word_b) else None,
                "pos_a": src if tag != "insert" else None,
                "pos_b": dst if tag != "delete" else None,
            }
            result.append(entry)
        return result
    except ImportError:
        # Simple character diff fallback
        pairs = []
        for i, (ca, cb) in enumerate(zip(word_a, word_b)):
            if ca != cb:
                pairs.append({"op": "replace", "char_a": ca, "char_b": cb, "pos_a": i, "pos_b": i})
        return pairs


def _conflict_chars_summary(word_a: Optional[str], word_b: Optional[str]) -> Optional[str]:
    """Return a human-readable conflict summary string like '24 vs 29'."""
    if not word_a or not word_b:
        return None
    if word_a == word_b:
        return None
    return f"{word_a} vs {word_b}"


class TextHypothesisAligner:
    """ROVER-inspired multi-model text alignment engine.

    Aligns up to 3 OCR candidate sequences for the same document region,
    producing a structured alignment lattice with per-position agreement
    classification and character-level conflict evidence.
    """

    def align(
        self,
        region_id: str,
        candidates: List[HypothesisCandidate],
    ) -> AlignedHypotheses:
        """Align multiple model hypotheses for a single document region.

        Args:
            region_id: The OCR region identifier.
            candidates: List of HypothesisCandidate (one per model). May be 1-3 entries.

        Returns:
            AlignedHypotheses with per-position lattice and overall agreement level.
        """
        if not candidates:
            return AlignedHypotheses(
                region_id=region_id,
                overall_agreement=AgreementLevel.SINGLE_MODEL_ONLY,
            )

        if len(candidates) == 1:
            tokens = candidates[0].word_tokens
            positions = [
                AlignedPosition(
                    position=i,
                    agreement=AgreementLevel.SINGLE_MODEL_ONLY,
                    candidates_at_position={candidates[0].source_model: w},
                    conflict_chars=None,
                    is_critical=_is_critical_token(w),
                )
                for i, w in enumerate(tokens)
            ]
            return AlignedHypotheses(
                region_id=region_id,
                candidates=candidates,
                positions=positions,
                overall_agreement=AgreementLevel.SINGLE_MODEL_ONLY,
            )

        # Generate all pairwise alignments
        pairwise_ops: Dict[str, List[Dict[str, Any]]] = {}
        model_names = [c.source_model for c in candidates]

        for idx_a in range(len(candidates)):
            for idx_b in range(idx_a + 1, len(candidates)):
                ca = candidates[idx_a]
                cb = candidates[idx_b]
                key = f"{ca.source_model}_vs_{cb.source_model}"
                ops = _word_editops(ca.word_tokens, cb.word_tokens)
                # Enrich SUBSTITUTION ops with char-level detail
                for op in ops:
                    if op["op_type"] == AlignOpType.SUBSTITUTION:
                        op["char_ops"] = _char_editops(
                            op.get("src_word") or "", op.get("dst_word") or ""
                        )
                pairwise_ops[key] = ops

        # Build merged lattice from the first pair as anchor
        positions = self._build_lattice(candidates, pairwise_ops)

        # Determine overall agreement (worst case across all positions)
        overall = AgreementLevel.FULL_AGREEMENT
        priority = [
            AgreementLevel.FULL_DISAGREEMENT,
            AgreementLevel.MISSING_TEXT,
            AgreementLevel.EXTRA_TEXT,
            AgreementLevel.MINORITY_DISAGREEMENT,
            AgreementLevel.SINGLE_MODEL_ONLY,
            AgreementLevel.FULL_AGREEMENT,
        ]
        for pos in positions:
            idx_pos = priority.index(pos.agreement) if pos.agreement in priority else len(priority)
            idx_overall = priority.index(overall) if overall in priority else len(priority)
            if idx_pos < idx_overall:
                overall = pos.agreement

        return AlignedHypotheses(
            region_id=region_id,
            candidates=candidates,
            positions=positions,
            pairwise_ops=pairwise_ops,
            overall_agreement=overall,
        )

    def _build_lattice(
        self,
        candidates: List[HypothesisCandidate],
        pairwise_ops: Dict[str, List[Dict[str, Any]]],
    ) -> List[AlignedPosition]:
        """Merge pairwise edit ops into a per-position agreement lattice.

        Uses the first candidate as the reference anchor sequence.
        Iterates over reference positions; maps other candidates' words at each position.
        """
        if not candidates:
            return []

        ref = candidates[0]
        ref_tokens = ref.word_tokens

        # Build map: for each non-reference candidate, what word do they have at
        # each reference-token position (None if deleted/inserted)?
        model_word_at_ref_pos: Dict[str, Dict[int, Optional[str]]] = {}
        model_insertions_at_ref_pos: Dict[str, Dict[int, List[str]]] = {}

        for idx_other in range(1, len(candidates)):
            other = candidates[idx_other]
            key = f"{ref.source_model}_vs_{other.source_model}"
            ops = pairwise_ops.get(key, [])
            word_map: Dict[int, Optional[str]] = {}
            ins_map: Dict[int, List[str]] = {}

            for op in ops:
                op_type = op.get("op_type")
                src_pos = op.get("src_pos")
                if op_type == AlignOpType.MATCH:
                    # Other candidate has same word at this reference position
                    if src_pos is not None:
                        word_map[src_pos] = op.get("src_word")
                elif op_type == AlignOpType.SUBSTITUTION:
                    if src_pos is not None:
                        word_map[src_pos] = op.get("dst_word")  # other model's word
                elif op_type == AlignOpType.DELETION:
                    if src_pos is not None:
                        word_map[src_pos] = None  # other model deleted this word
                elif op_type == AlignOpType.INSERTION:
                    sp = src_pos if src_pos is not None else 0
                    dw = op.get("dst_word")
                    if dw:
                        ins_map.setdefault(sp, []).append(dw)

            model_word_at_ref_pos[other.source_model] = word_map
            model_insertions_at_ref_pos[other.source_model] = ins_map

        positions: List[AlignedPosition] = []
        for i, ref_word in enumerate(ref_tokens):
            candidates_at: Dict[str, Optional[str]] = {ref.source_model: ref_word}

            for other_model, word_map in model_word_at_ref_pos.items():
                candidates_at[other_model] = word_map.get(i, ref_word)  # default MATCH if not in ops

            # Determine agreement level
            words_present = {w for w in candidates_at.values() if w is not None}
            words_absent = [m for m, w in candidates_at.items() if w is None]

            # Normalize for agreement comparison
            normalized_words = {_normalize(w) for w in words_present}

            if len(words_absent) > 0 and len(words_present) == 1:
                agreement = AgreementLevel.MISSING_TEXT
                conflict_chars = None
            elif len(normalized_words) == 1:
                agreement = AgreementLevel.FULL_AGREEMENT
                conflict_chars = None
            elif len(normalized_words) == 2 and len(candidates) > 2:
                # Majority agrees; one model disagrees
                word_counts: Dict[str, int] = {}
                for w in candidates_at.values():
                    if w is not None:
                        nw = _normalize(w)
                        word_counts[nw] = word_counts.get(nw, 0) + 1
                majority_count = max(word_counts.values())
                if majority_count >= 2:
                    agreement = AgreementLevel.MINORITY_DISAGREEMENT
                else:
                    agreement = AgreementLevel.FULL_DISAGREEMENT
                # Build conflict summary from raw (not normalized) words
                raw_words = sorted(set(w for w in candidates_at.values() if w is not None))
                conflict_chars = " vs ".join(raw_words) if len(raw_words) > 1 else None
            elif len(normalized_words) > 1:
                agreement = AgreementLevel.FULL_DISAGREEMENT
                raw_words = sorted(set(w for w in candidates_at.values() if w is not None))
                conflict_chars = " vs ".join(raw_words) if len(raw_words) > 1 else None
            else:
                agreement = AgreementLevel.FULL_AGREEMENT
                conflict_chars = None

            is_crit = _is_critical_token(ref_word)

            positions.append(AlignedPosition(
                position=i,
                agreement=agreement,
                candidates_at_position=candidates_at,
                conflict_chars=conflict_chars,
                is_critical=is_crit,
            ))

        for other_model, ins_map in model_insertions_at_ref_pos.items():
            for sp, ins_words in ins_map.items():
                for ins_word in ins_words:
                    cand_at = {ref.source_model: None}
                    for m in candidates:
                        cand_at[m.source_model] = ins_word if m.source_model == other_model else None
                    
                    positions.append(AlignedPosition(
                        position=len(positions),
                        agreement=AgreementLevel.EXTRA_TEXT,
                        candidates_at_position=cand_at,
                        conflict_chars=f"inserted: {ins_word}",
                        is_critical=_is_critical_token(ins_word),
                    ))

        return positions

    def build_hypothesis_candidate(
        self,
        source_model: str,
        model_version: str,
        raw_text: str,
        raw_confidence: Optional[float] = None,
    ) -> HypothesisCandidate:
        """Construct a HypothesisCandidate from raw model output.

        The raw_text is stored unmodified. normalized_text is computed
        for alignment purposes only.
        """
        tokens = _tokenize(raw_text)
        return HypothesisCandidate(
            source_model=source_model,
            model_version=model_version,
            raw_text=raw_text,
            normalized_text=_normalize(raw_text),
            raw_confidence=raw_confidence,
            word_tokens=tokens,
        )
