from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TelegramWebhookActivationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    webhook_url: str
    webhook_secret: str


class TelegramWebhookStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    webhook_url: str
    status: str
    last_verified_at: str | None
