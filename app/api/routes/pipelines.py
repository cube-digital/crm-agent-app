"""Pipelines + stages (read-only, seeded per tenant)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import PipelineOut, StageOut
from app.auth.deps import Principal, get_db, get_principal
from app.db.models import Pipeline, PipelineStage

router = APIRouter(tags=["pipelines"])


@router.get("/pipelines", response_model=list[PipelineOut])
def list_pipelines(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return list(db.scalars(
        select(Pipeline).where(Pipeline.company_id == principal.company_id)
        .order_by(Pipeline.display_order)
    ))


@router.get("/pipelines/{pipeline_id}/stages", response_model=list[StageOut])
def list_stages(pipeline_id: str, principal: Principal = Depends(get_principal),
                db: Session = Depends(get_db)):
    pipeline = db.get(Pipeline, pipeline_id)
    if pipeline is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    if pipeline.company_id != principal.company_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
    return list(db.scalars(
        select(PipelineStage).where(
            PipelineStage.company_id == principal.company_id,
            PipelineStage.pipeline_id == pipeline_id,
        ).order_by(PipelineStage.display_order)
    ))
