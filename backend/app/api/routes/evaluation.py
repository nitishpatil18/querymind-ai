from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import Container, get_container
from app.services.evaluation_service import EvalProgress, EvalReport

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


class EvalRunRequest(BaseModel):
    mode: Literal["full", "retrieval_only"] | None = None
    resume: bool = False  # keep earlier answers that did not fail, run only the unfinished questions


class EvalResults(BaseModel):
    progress: EvalProgress
    report: EvalReport | None = None


@router.post("/run", response_model=EvalProgress, status_code=202, summary="Start the golden-dataset evaluation in the background")
def run_evaluation(body: EvalRunRequest | None = None, c: Container = Depends(get_container)) -> EvalProgress:
    return c.evaluation_service.start_background(body.mode if body else None, body.resume if body else False)


@router.get("/results", response_model=EvalResults, summary="Latest measured evaluation results and run progress")
def evaluation_results(c: Container = Depends(get_container)) -> EvalResults:
    return EvalResults(progress=c.evaluation_service.progress, report=c.evaluation_service.latest())
