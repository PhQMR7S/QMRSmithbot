from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from qmrsmithbot.api.auth import router as auth_router
from qmrsmithbot.api.preferences import router as preferences_router
from qmrsmithbot.api.projects import router as projects_router
from qmrsmithbot.api.telegram import router as telegram_router
from qmrsmithbot.api.telegram_webhook import router as telegram_webhook_router
from qmrsmithbot.api.templates import router as templates_router
from qmrsmithbot.api.tenants import router as tenants_router
from qmrsmithbot.auth.authorization import AuthorizationDenied
from qmrsmithbot.auth.service import (
    AuthenticationError,
    TenantAccessError,
    TenantAdministrationError,
    TenantSelectionRequired,
)
from qmrsmithbot.db.session import close_database
from qmrsmithbot.projects.service import (
    InvalidWorkflowError,
    ProjectNotFoundError,
    VersionNotFoundError,
)
from qmrsmithbot.rate_limit import close_rate_limiter
from qmrsmithbot.request_context import (
    attach_request_id,
    reset_request_id,
    set_request_id,
)
from qmrsmithbot.telegram.provisioning import TelegramBotAlreadyAssigned, TelegramProvisioningError
from qmrsmithbot.telegram.webhook_service import TelegramWebhookError, TelegramWebhookNotReady


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await close_rate_limiter()
        await close_database()


app = FastAPI(title="QMRSmithbot", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(preferences_router)
app.include_router(projects_router)
app.include_router(tenants_router)
app.include_router(templates_router)
app.include_router(telegram_router)
app.include_router(telegram_webhook_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = attach_request_id(request)
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers["X-Request-ID"] = request_id
    return response


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


@app.exception_handler(TenantAdministrationError)
async def tenant_administration_error(_: Request, exc: TenantAdministrationError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(TenantAccessError)
async def tenant_access_error(_: Request, exc: TenantAccessError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(TelegramBotAlreadyAssigned)
async def telegram_bot_already_assigned(_: Request, exc: TelegramBotAlreadyAssigned) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(TelegramProvisioningError)
async def telegram_provisioning_error(_: Request, exc: TelegramProvisioningError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(TelegramWebhookNotReady)
async def telegram_webhook_not_ready(_: Request, exc: TelegramWebhookNotReady) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(TelegramWebhookError)
async def telegram_webhook_error(_: Request, exc: TelegramWebhookError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "QMRSmithbot"}
