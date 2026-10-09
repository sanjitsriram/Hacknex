from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from evidence_ocr.fusion.service import FusionService
from evidence_ocr.models.fusion import FusionRun, FusionStatus
from evidence_ocr.models.region import BoundingBox, CandidateSuggestion, RegionEntity


@pytest.mark.asyncio
async def test_fusion_uses_repository_contract_and_latest_page_blocks():
    region = RegionEntity(
        id='r1', document_id='doc1', line='A', original='A', reason='',
        bounding_box=BoundingBox(x=0, y=0, w=10, h=10),
        candidates_detail=[CandidateSuggestion(text='A', provider_id='trocr', model_version='pinned')],
        created_at='2026-10-09T00:00:00Z', updated_at='2026-10-09T00:00:00Z',
    )
    class Regions:
        async def list_by_document(self, document_id):
            assert document_id == 'doc1'
            return [region]
    latest_block = object()
    parsing = SimpleNamespace(list_by_document=AsyncMock(return_value=[
        SimpleNamespace(pages=[SimpleNamespace(blocks=[latest_block])]),
        SimpleNamespace(pages=[SimpleNamespace(blocks=[object()])]),
    ]))
    service = FusionService(region_repo=Regions(), parsing_repo=parsing)
    service._alignment_svc = MagicMock()
    service._alignment_svc.align.return_value = []
    service._disagreement_detector = MagicMock()
    service._disagreement_detector.detect.return_value = []
    service._selection_svc = MagicMock()
    service._selection_svc.propose.return_value = SimpleNamespace(auto_proposable=False, requires_review=True)
    run = FusionRun(id='f1', document_id='doc1', created_by_session='test',
                    created_at='2026-10-09T00:00:00Z', updated_at='2026-10-09T00:00:00Z')
    result = await service.execute_fusion(run, 'doc1', None, 'image/png')
    assert result.status == FusionStatus.COMPLETED
    assert result.region_count == 1
    assert service._alignment_svc.align.call_args.kwargs['vl_blocks'] == [latest_block]
    hypotheses = service._selection_svc.propose.call_args.kwargs['aligned'].candidates
    assert hypotheses[0].source_model == 'trocr'
    assert hypotheses[0].raw_text == 'A'
