from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from qmrsmithbot.api.auth import router as auth_router
from qmrsmithbot.api.projects import router as projects_router
from qmrsmithbot.auth.authorization import AuthorizationDenied
from qmrsmithbot.auth.service import AuthenticationError, TenantAccessError, TenantSelectionRequired
from qmrsmithbot.projects.service import InvalidWorkflowError, ProjectNotFoundError, VersionNotFoundError

app = FastAPI(title="QMRSmithbot", version="0.1.0")
app.include_router(auth_router)
app.include_router(projects_router)


@app.exception_handler(ProjectNotFoundError)
async def project_not_found(_: Request, exc: ProjectNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(VersionNotFoundError)
async def version_not_found(_: Request, exc: VersionNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidWorkflowError)
async def invalid_workflow(_: Request, exc: InvalidWorkflowError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(AuthenticationError)
async def authentication_error(_: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(AuthorizationDenied)
async def authorization_denied(_: Request, exc: AuthorizationDenied) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(TenantSelectionRequired)
async def tenant_selection_required(_: Request, exc: TenantSelectionRequired) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(TenantAccessError)
async def tenant_access_error(_: Request, exc: TenantAccessError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "QMRSmithbot"}
