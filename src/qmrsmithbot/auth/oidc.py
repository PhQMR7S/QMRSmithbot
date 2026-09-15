from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from jwt import PyJWK
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.auth.models import Principal
from qmrsmithbot.auth.service import SessionService, TenantService
from qmrsmithbot.config import settings
from qmrsmithbot.db.models import IdentityRecord, OIDCLoginStateRecord, User


class OIDCError(Exception):
    """Raised when an OIDC transaction cannot be completed safely."""


class IdentityAlreadyLinked(OIDCError):
    """Raised when an external identity is already linked to another user."""


@dataclass(frozen=True, slots=True)
class OIDCProfile:
    provider: str
    subject: str
    email: str | None
    email_verified: bool
    username: str | None
    first_name: str | None


class OIDCService:
    provider_name = "oidc"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=False
        )

    async def close(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _fernet() -> Fernet:
        key = settings.auth_state_encryption_key.get_secret_value().strip().encode("ascii")
        try:
            return Fernet(key)
        except (ValueError, TypeError) as exc:
            raise OIDCError("invalid AUTH_STATE_ENCRYPTION_KEY") from exc

    async def _metadata(self) -> dict[str, object]:
        issuer = settings.auth_oidc_issuer.rstrip("/")
        if not issuer.startswith("https://"):
            raise OIDCError("OIDC issuer must use HTTPS")
        response = await self._http.get(f"{issuer}/.well-known/openid-configuration")
        response.raise_for_status()
        metadata = response.json()
        if metadata.get("issuer") != issuer:
            raise OIDCError("OIDC discovery issuer mismatch")
        authorization_endpoint = metadata.get("authorization_endpoint")
        token_endpoint = metadata.get("token_endpoint")
        jwks_uri = metadata.get("jwks_uri")
        if not all(
            isinstance(value, str) and value.startswith("https://")
            for value in (authorization_endpoint, token_endpoint, jwks_uri)
        ):
            raise OIDCError("OIDC discovery contains invalid HTTPS endpoints")
        return metadata

    async def begin(self, *, user_id: int | None = None) -> str:
        if not settings.auth_oidc_enabled:
            raise OIDCError("OIDC authentication is disabled")
        metadata = await self._metadata()
        methods = metadata.get("code_challenge_methods_supported", [])
        if not isinstance(methods, list) or "S256" not in methods:
            raise OIDCError("OIDC provider must support PKCE S256")

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        record = OIDCLoginStateRecord(
            id=uuid4(),
            state_hash=self._hash(state),
            nonce_hash=self._hash(nonce),
            code_verifier_ciphertext=self._fernet().encrypt(verifier.encode()).decode("ascii"),
            provider=self.provider_name,
            user_id=user_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        self.session.add(record)
        await self.session.flush()
        params = {
            "response_type": "code",
            "client_id": settings.auth_oidc_client_id,
            "redirect_uri": settings.auth_oidc_redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{metadata['authorization_endpoint']}?{urlencode(params)}"

    async def callback(self, *, code: str, state: str) -> tuple[Principal, str, datetime]:
        if not code or len(code) > 4096 or not state or len(state) > 512:
            raise OIDCError("invalid OIDC callback parameters")
        record = await self.session.scalar(
            select(OIDCLoginStateRecord).where(
                OIDCLoginStateRecord.state_hash == self._hash(state),
                OIDCLoginStateRecord.used_at.is_(None),
                OIDCLoginStateRecord.expires_at > datetime.now(UTC),
            )
        )
        if record is None:
            raise OIDCError("invalid or expired OIDC state")
        now = datetime.now(UTC)
        record.used_at = now
        await self.session.flush()
        try:
            verifier = self._fernet().decrypt(record.code_verifier_ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise OIDCError("OIDC transaction state is invalid") from exc

        metadata = await self._metadata()
        token_response = await self._http.post(
            str(metadata["token_endpoint"]),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.auth_oidc_redirect_uri,
                "client_id": settings.auth_oidc_client_id,
                "client_secret": settings.auth_oidc_client_secret.get_secret_value(),
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        tokens = token_response.json()
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str):
            raise OIDCError("OIDC token response did not contain an ID token")

        profile = await self._verify_id_token(
            id_token, metadata=metadata, expected_nonce_hash=record.nonce_hash
        )
        user_id = await self._resolve_identity(profile, linked_user_id=record.user_id)
        await TenantService(self.session).ensure_personal_tenant(user_id)
        principal, access_token, expires_at = await SessionService(self.session).create_session(
            user_id=user_id
        )
        return principal, access_token, expires_at

    async def _verify_id_token(
        self,
        id_token: str,
        *,
        metadata: dict[str, object],
        expected_nonce_hash: str,
    ) -> OIDCProfile:
        header = jwt.get_unverified_header(id_token)
        kid = header.get("kid")
        algorithm = header.get("alg")
        if not isinstance(kid, str) or algorithm not in {"RS256", "PS256", "ES256"}:
            raise OIDCError("OIDC ID token uses an unsupported signing configuration")
        response = await self._http.get(str(metadata["jwks_uri"]))
        response.raise_for_status()
        keys = response.json().get("keys", [])
        jwk = next((key for key in keys if key.get("kid") == kid), None)
        if jwk is None:
            raise OIDCError("OIDC signing key was not found")
        try:
            key = PyJWK(jwk, algorithm=algorithm).key
            claims = jwt.decode(
                id_token,
                key=key,
                algorithms=[algorithm],
                audience=settings.auth_oidc_client_id,
                issuer=settings.auth_oidc_issuer.rstrip("/"),
                options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]},
            )
        except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
            raise OIDCError("OIDC ID token validation failed") from exc
        nonce = claims.get("nonce")
        if not isinstance(nonce, str) or self._hash(nonce) != expected_nonce_hash:
            raise OIDCError("OIDC nonce validation failed")
        azp = claims.get("azp")
        audience = claims.get("aud")
        if isinstance(audience, list) and len(audience) > 1 and azp != settings.auth_oidc_client_id:
            raise OIDCError("OIDC authorized-party validation failed")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise OIDCError("OIDC subject is missing")
        email = claims.get("email")
        if email is not None and not isinstance(email, str):
            raise OIDCError("OIDC email claim is invalid")
        return OIDCProfile(
            provider=self.provider_name,
            subject=subject,
            email=email.strip().lower() if email else None,
            email_verified=claims.get("email_verified") is True,
            username=(
                claims.get("preferred_username")
                if isinstance(claims.get("preferred_username"), str)
                else None
            ),
            first_name=(
                claims.get("given_name") if isinstance(claims.get("given_name"), str) else None
            ),
        )

    async def _resolve_identity(self, profile: OIDCProfile, *, linked_user_id: int | None) -> int:
        identity = await self.session.scalar(
            select(IdentityRecord).where(
                IdentityRecord.provider == profile.provider,
                IdentityRecord.subject == profile.subject,
            )
        )
        if identity is not None:
            if linked_user_id is not None and identity.user_id != linked_user_id:
                raise IdentityAlreadyLinked("external identity is linked to another user")
            identity.email = profile.email
            identity.email_verified = profile.email_verified
            identity.last_authenticated_at = datetime.now(UTC)
            await self.session.flush()
            return identity.user_id

        if linked_user_id is not None:
            user_id = linked_user_id
        else:
            user_id = await self._create_external_user(profile)
        self.session.add(
            IdentityRecord(
                user_id=user_id,
                provider=profile.provider,
                subject=profile.subject,
                email=profile.email,
                email_verified=profile.email_verified,
                last_authenticated_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return user_id

    async def _create_external_user(self, profile: OIDCProfile) -> int:
        for _ in range(5):
            user_id = secrets.randbelow(2**62 - 1) + 1
            if await self.session.get(User, user_id) is None:
                self.session.add(
                    User(id=user_id, username=profile.username, first_name=profile.first_name)
                )
                await self.session.flush()
                return user_id
        raise OIDCError("could not allocate an internal user identifier")
