"""FastAPI host for the lightweight Shopping Copilot evaluation console."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .evaluation_service import EvaluationJobs, EvaluationService, jobs, service


APP_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = APP_ROOT / "static"


def create_app(
    service_instance: EvaluationService = service,
    jobs_instance: EvaluationJobs = jobs,
) -> FastAPI:
    """Create the HTTP shell; injectable dependencies keep API tests lightweight."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        service_instance.start_loading()
        yield

    application = FastAPI(
        title="Shopping Copilot Evaluation API",
        version="2.0.0",
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @application.get("/api/health")
    def health() -> dict[str, Any]:
        status = service_instance.status
        return {"ok": not bool(status["error"]), **status}

    @application.get("/api/bootstrap")
    def bootstrap() -> dict[str, Any]:
        status = service_instance.status
        if not status["ready"]:
            raise HTTPException(
                status_code=425,
                detail=status["error"] or "Catalog index is still building",
            )
        try:
            return {
                "config": "default.json",
                "samples": service_instance.list_samples(),
                "report": service_instance.best_completed_run(),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=repr(exc)) from exc

    @application.post("/api/session/run")
    def run_session(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            return service_instance.run_single(
                str(payload.get("sampleId") or ""),
                max(0, min(2, int(payload.get("paraphraseLevel") or 0))),
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=425, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=repr(exc)) from exc

    @application.post("/api/eval/jobs")
    def create_job(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        requested_config = str(payload.get("config") or "default.json")
        if requested_config != "default.json":
            raise HTTPException(status_code=400, detail="Only default.json is supported")
        try:
            return jobs_instance.create(
                max(0, min(2, int(payload.get("paraphraseLevel") or 0))),
                int(payload.get("limit") or 200),
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=425, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=repr(exc)) from exc

    @application.get("/api/eval/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            return jobs_instance.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}") from exc

    return application


app = create_app()


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    import uvicorn

    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=False)
