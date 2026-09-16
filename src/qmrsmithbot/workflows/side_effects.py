from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.telegram.client import TelegramBotClientFactory
from qmrsmithbot.workflows.action_policy import (
    ActionPolicyError,
    resolve_and_validate_host,
    validate_http_url,
    validate_redirect,
)
from qmrsmithbot.workflows.actions import (
    ActionExecutionError,
    ActionFailureKind,
    ActionHandler,
    ActionResult,
)
from qmrsmithbot.workflows.executor import ExecutionContext
from qmrsmithbot.workflows.schema import WorkflowNode


class HttpTransport(Protocol):
    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, dict[str, str], bytes]: ...


@dataclass(frozen=True, slots=True)
class SideEffectLimits:
    max_message_length: int = 4096
    max_http_body_bytes: int = 256 * 1024
    max_http_response_bytes: int = 256 * 1024
    max_redirects: int = 3
    max_headers: int = 32


class TelegramActionHandler(ActionHandler):
    action_type: str

    def __init__(self, session: AsyncSession, *, limits: SideEffectLimits | None = None) -> None:
        self.client_factory = TelegramBotClientFactory(session)
        self.limits = limits or SideEffectLimits()

    @staticmethod
    def _project_id(context: ExecutionContext) -> UUID:
        value = context.project_id
        if not value:
            raise ActionExecutionError(
                "action execution is missing project identity",
                kind=ActionFailureKind.NON_RETRYABLE,
            )
        try:
            return UUID(value)
        except ValueError as exc:
            raise ActionExecutionError(
                "action execution has an invalid project identity",
                kind=ActionFailureKind.NON_RETRYABLE,
            ) from exc

    @staticmethod
    def _chat_id(context: ExecutionContext, config: dict[str, Any]) -> int:
        value = config.get("chat_id", context.chat_id)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ActionExecutionError(
                "Telegram action requires an integer chat_id",
                kind=ActionFailureKind.NON_RETRYABLE,
            )
        return value

    def _text(self, config: dict[str, Any]) -> str:
        text = config.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ActionExecutionError(
                "Telegram message action requires non-empty text",
                kind=ActionFailureKind.NON_RETRYABLE,
            )
        if len(text) > self.limits.max_message_length:
            raise ActionExecutionError(
                "Telegram message exceeds the configured length limit",
                kind=ActionFailureKind.NON_RETRYABLE,
            )
        return text

    @staticmethod
    def _message_id(config: dict[str, Any], context: ExecutionContext) -> int:
        value = config.get("message_id", context.values.get("message_id"))
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ActionExecutionError(
                "Telegram action requires a positive integer message_id",
                kind=ActionFailureKind.NON_RETRYABLE,
            )
        return value

    @staticmethod
    def _map_telegram_error(exc: Exception) -> ActionExecutionError:
        if isinstance(exc, TelegramRetryAfter):
            return ActionExecutionError(
                "Telegram requested a retry", kind=ActionFailureKind.RETRYABLE
            )
        if isinstance(exc, (TelegramServerError, TelegramNetworkError, TimeoutError)):
            return ActionExecutionError(
                "Telegram request failed temporarily", kind=ActionFailureKind.RETRYABLE
            )
        if isinstance(exc, TelegramBadRequest):
            return ActionExecutionError(
                "Telegram rejected the action", kind=ActionFailureKind.NON_RETRYABLE
            )
        return ActionExecutionError("Telegram action failed", kind=ActionFailureKind.NON_RETRYABLE)


class SendMessageActionHandler(TelegramActionHandler):
    action_type = "action.message"

    async def execute(
        self, *, node: WorkflowNode, context: ExecutionContext, attempt: int
    ) -> ActionResult:
        config = node.config
        chat_id = self._chat_id(context, config)
        text = self._text(config)
        project_id = self._project_id(context)
        try:
            async with self.client_factory.bot(project_id) as bot:
                message = await bot.send_message(chat_id=chat_id, text=text)
        except Exception as exc:
            raise self._map_telegram_error(exc) from exc
        return ActionResult(
            action_type=self.action_type,
            external_key=f"telegram:{project_id}:message:{message.message_id}",
            attempt=attempt,
            metadata={"message_id": message.message_id, "chat_id": chat_id},
        )


class EditMessageActionHandler(TelegramActionHandler):
    action_type = "action.edit_message"

    async def execute(
        self, *, node: WorkflowNode, context: ExecutionContext, attempt: int
    ) -> ActionResult:
        config = node.config
        chat_id = self._chat_id(context, config)
        message_id = self._message_id(config, context)
        text = self._text(config)
        project_id = self._project_id(context)
        try:
            async with self.client_factory.bot(project_id) as bot:
                message = await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                )
        except Exception as exc:
            raise self._map_telegram_error(exc) from exc
        return ActionResult(
            action_type=self.action_type,
            external_key=f"telegram:{project_id}:message:{message_id}:edit",
            attempt=attempt,
            metadata={"message_id": message.message_id, "chat_id": chat_id},
        )


class DeleteMessageActionHandler(TelegramActionHandler):
    action_type = "action.delete_message"

    async def execute(
        self, *, node: WorkflowNode, context: ExecutionContext, attempt: int
    ) -> ActionResult:
        config = node.config
        chat_id = self._chat_id(context, config)
        message_id = self._message_id(config, context)
        project_id = self._project_id(context)
        try:
            async with self.client_factory.bot(project_id) as bot:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as exc:
            raise self._map_telegram_error(exc) from exc
        return ActionResult(
            action_type=self.action_type,
            external_key=f"telegram:{project_id}:message:{message_id}:delete",
            attempt=attempt,
            metadata={"message_id": message_id, "chat_id": chat_id},
        )


class HttpActionHandler(ActionHandler):
    action_type = "action.http"

    def __init__(self, transport: HttpTransport, *, limits: SideEffectLimits | None = None) -> None:
        self.transport = transport
        self.limits = limits or SideEffectLimits()

    @staticmethod
    def _method(config: dict[str, Any]) -> str:
        method = config.get("method", "GET")
        if not isinstance(method, str):
            raise ActionExecutionError(
                "HTTP method must be a string", kind=ActionFailureKind.NON_RETRYABLE
            )
        method = method.upper().strip()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ActionExecutionError(
                "HTTP method is not allowed", kind=ActionFailureKind.NON_RETRYABLE
            )
        return method

    def _headers(self, config: dict[str, Any]) -> dict[str, str]:
        raw = config.get("headers", {})
        if not isinstance(raw, dict) or len(raw) > self.limits.max_headers:
            raise ActionExecutionError(
                "HTTP headers are invalid or exceed the configured limit",
                kind=ActionFailureKind.NON_RETRYABLE,
            )
        headers: dict[str, str] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, str) or not key.strip():
                raise ActionExecutionError(
                    "HTTP headers must contain string key/value pairs",
                    kind=ActionFailureKind.NON_RETRYABLE,
                )
            if key.lower() in {"host", "content-length", "transfer-encoding"}:
                raise ActionExecutionError(
                    "HTTP action does not permit restricted transport headers",
                    kind=ActionFailureKind.NON_RETRYABLE,
                )
            headers[key] = value
        return headers

    @staticmethod
    def _body(config: dict[str, Any], limit: int) -> bytes | None:
        value = config.get("body")
        if value is None:
            return None
        if isinstance(value, str):
            body = value.encode("utf-8")
        elif isinstance(value, (bytes, bytearray)):
            body = bytes(value)
        else:
            raise ActionExecutionError(
                "HTTP body must be text or bytes", kind=ActionFailureKind.NON_RETRYABLE
            )
        if len(body) > limit:
            raise ActionExecutionError(
                "HTTP request body exceeds the configured limit",
                kind=ActionFailureKind.NON_RETRYABLE,
            )
        return body

    async def execute(
        self, *, node: WorkflowNode, context: ExecutionContext, attempt: int
    ) -> ActionResult:
        config = node.config
        raw_url = config.get("url")
        if not isinstance(raw_url, str):
            raise ActionExecutionError(
                "HTTP action requires a URL", kind=ActionFailureKind.NON_RETRYABLE
            )
        try:
            url = validate_http_url(raw_url)
            parsed = urlsplit(url)
            resolved = resolve_and_validate_host(parsed.hostname or "")
        except ActionPolicyError as exc:
            raise ActionExecutionError(str(exc), kind=ActionFailureKind.NON_RETRYABLE) from exc

        method = self._method(config)
        headers = self._headers(config)
        body = self._body(config, self.limits.max_http_body_bytes)
        timeout = context.remaining_seconds()
        effective_timeout = 15.0 if timeout is None else min(15.0, timeout)
        if effective_timeout <= 0:
            raise ActionExecutionError(
                "workflow deadline exceeded before HTTP action", kind=ActionFailureKind.RETRYABLE
            )

        current_url = url
        redirects = 0
        while True:
            try:
                status, response_headers, response_body = await self.transport.request(
                    method=method,
                    url=current_url,
                    headers=headers,
                    body=body,
                    timeout=effective_timeout,
                )
            except TimeoutError as exc:
                raise ActionExecutionError(
                    "HTTP request timed out", kind=ActionFailureKind.RETRYABLE
                ) from exc
            except OSError as exc:
                raise ActionExecutionError(
                    "HTTP request failed temporarily", kind=ActionFailureKind.RETRYABLE
                ) from exc

            if status in {301, 302, 303, 307, 308}:
                location = response_headers.get("location")
                if not location or redirects >= self.limits.max_redirects:
                    raise ActionExecutionError(
                        "HTTP redirect policy rejected the response",
                        kind=ActionFailureKind.NON_RETRYABLE,
                    )
                try:
                    current_url = validate_redirect(location)
                    parsed_host = urlsplit(current_url).hostname
                    resolve_and_validate_host(parsed_host or "")
                except ActionPolicyError as exc:
                    raise ActionExecutionError(
                        str(exc), kind=ActionFailureKind.NON_RETRYABLE
                    ) from exc
                redirects += 1
                continue

            if len(response_body) > self.limits.max_http_response_bytes:
                raise ActionExecutionError(
                    "HTTP response exceeds the configured size limit",
                    kind=ActionFailureKind.NON_RETRYABLE,
                )
            if 500 <= status <= 599:
                raise ActionExecutionError(
                    f"HTTP endpoint returned {status}", kind=ActionFailureKind.RETRYABLE
                )

            return ActionResult(
                action_type=self.action_type,
                external_key=f"http:{context.trace_id}:{node.id}",
                attempt=attempt,
                metadata={
                    "status": status,
                    "content_length": len(response_body),
                    "resolved_addresses": [item.address for item in resolved],
                },
            )


class AiohttpHttpTransport:
    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, dict[str, str], bytes]:
        import aiohttp

        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(
            timeout=client_timeout,
            raise_for_status=False,
        ) as session, session.request(
            method,
            url,
            headers=headers,
            data=body,
            allow_redirects=False,
        ) as response:
            response_body = await response.read()
            return (
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                response_body,
            )
