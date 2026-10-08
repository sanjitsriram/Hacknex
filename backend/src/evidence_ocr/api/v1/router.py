"""Aggregates all API v1 routers."""

from fastapi import APIRouter
from evidence_ocr.api.v1.endpoints import (
    documents_router,
    evaluations_router,
    health_router,
    jobs_router,
    review_router,
)

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(review_router)
api_v1_router.include_router(evaluations_router)
