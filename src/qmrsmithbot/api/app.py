from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from qmrsmithbot.api.projects import router as projects_router
from qmrsmithbot.config import settings
from qmrsmithbot.projects.service import (
    InvalidWorkflowError,
    ProjectNotFoundError,
    VersionNotFoundError,
)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(projects_router)


@app.exception_handler(ProjectNotFoundError)
async def project_not_found_handler(_request: Request, exc: ProjectNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(VersionNotFoundError)
async def version_not_found_handler(_request: Request, exc: VersionNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidWorkflowError)
async def invalid_workflow_handler(_request: Request, exc: InvalidWorkflowError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
