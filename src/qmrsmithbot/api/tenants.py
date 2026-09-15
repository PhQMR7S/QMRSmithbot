from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qmrsmithbot.api.dependencies import (
    get_authorization_service,
    get_current_principal,
    get_current_tenant_id,
)
from qmrsmithbot.api.schemas import (
    MemberRoleRequest,
    OIDCStartResponse,
    OwnershipTransferRequest,
    TenantCreateRequest,
    TenantInvitationAcceptRequest,
    TenantInvitationCreateRequest,
    TenantInvitationResponse,
    TenantMemberResponse,
    TenantResponse,
)
from qmrsmithbot.auth.authorization import AuthorizationService
from qmrsmithbot.auth.models import ROLE_RANK, Permission, Principal, TenantRole
from qmrsmithbot.auth.service import TenantAdministrationError, TenantService
from qmrsmithbot.db.models import AuditEvent
from qmrsmithbot.db.session import get_session
from qmrsmithbot.request_context import get_request_id

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


def _tenant_response(tenant) -> TenantResponse:
    return TenantResponse(id=tenant.id, name=tenant.name, slug=tenant.slug)


async def _audit(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: int | None,
    tenant_id: UUID | None,
    metadata: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action=action,
            metadata_json=metadata or {},
            request_id=get_request_id(),
        )
    )
    await session.flush()


@router.get("", response_model=list[TenantResponse])
async def list_tenants(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TenantResponse]:
    tenants = await TenantService(session).list_tenants(principal.user_id)
    return [_tenant_response(tenant) for tenant in tenants]


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreateRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantResponse:
    try:
        tenant = await TenantService(session).create_tenant(
            user_id=principal.user_id, name=payload.name, slug=payload.slug
        )
    except TenantAdministrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _audit(
        session,
        action="tenant.created",
        actor_user_id=principal.user_id,
        tenant_id=tenant.id,
        metadata={"slug": tenant.slug},
    )
    return _tenant_response(tenant)


@router.get("/members", response_model=list[TenantMemberResponse])
async def list_members(
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TenantMemberResponse]:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.MEMBERS_READ
    )
    members = await TenantService(session).list_members(tenant_id)
    return [TenantMemberResponse(**member.__dict__) for member in members]


@router.post("/invitations", response_model=TenantInvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: TenantInvitationCreateRequest,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantInvitationResponse:
    membership = await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.INVITATIONS_MANAGE
    )
    if ROLE_RANK[membership.role] <= ROLE_RANK[payload.role]:
        raise HTTPException(status_code=403, detail="cannot invite an equal or higher privilege role")
    try:
        invitation_id, token, expires_at = await TenantService(session).create_invitation(
            tenant_id=tenant_id,
            invited_by_user_id=principal.user_id,
            email=payload.email,
            role=payload.role,
        )
    except TenantAdministrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _audit(
        session,
        action="tenant.invitation.created",
        actor_user_id=principal.user_id,
        tenant_id=tenant_id,
        metadata={"invitation_id": str(invitation_id), "role": payload.role.value},
    )
    return TenantInvitationResponse(
        invitation_id=invitation_id, expires_at=expires_at, invitation_token=token
    )


@router.post("/invitations/accept", response_model=TenantResponse)
async def accept_invitation(
    payload: TenantInvitationAcceptRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantResponse:
    try:
        tenant_id = await TenantService(session).accept_invitation(
            user_id=principal.user_id, raw_token=payload.invitation_token
        )
    except TenantAdministrationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    tenant = await session.get(__import__("qmrsmithbot.db.models", fromlist=["TenantRecord"]).TenantRecord, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant was not found")
    await _audit(
        session,
        action="tenant.invitation.accepted",
        actor_user_id=principal.user_id,
        tenant_id=tenant_id,
    )
    return TenantResponse(id=tenant.id, name=tenant.name, slug=tenant.slug)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: UUID,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.INVITATIONS_MANAGE
    )
    try:
        await TenantService(session).revoke_invitation(tenant_id=tenant_id, invitation_id=invitation_id)
    except TenantAdministrationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _audit(
        session,
        action="tenant.invitation.revoked",
        actor_user_id=principal.user_id,
        tenant_id=tenant_id,
        metadata={"invitation_id": str(invitation_id)},
    )


@router.patch("/members/{target_user_id}/role", response_model=TenantMemberResponse)
async def change_member_role(
    target_user_id: int,
    payload: MemberRoleRequest,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantMemberResponse:
    membership = await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.MEMBERS_MANAGE
    )
    try:
        await TenantService(session).change_role(
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            new_role=payload.role,
            actor_role=membership.role,
        )
    except TenantAdministrationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await _audit(
        session,
        action="tenant.member.role_changed",
        actor_user_id=principal.user_id,
        tenant_id=tenant_id,
        metadata={"target_user_id": target_user_id, "role": payload.role.value},
    )
    member = next(
        (item for item in await TenantService(session).list_members(tenant_id) if item.user_id == target_user_id),
        None,
    )
    if member is None:
        raise HTTPException(status_code=404, detail="member was not found")
    return TenantMemberResponse(
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        role=member.role,
        username=member.username,
        email=member.email,
    )


@router.post("/ownership/transfer", response_model=TenantMemberResponse)
async def transfer_ownership(
    payload: OwnershipTransferRequest,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantMemberResponse:
    membership = await authorization.membership(user_id=principal.user_id, tenant_id=tenant_id)
    if membership.role != TenantRole.OWNER:
        raise HTTPException(status_code=403, detail="only the owner can transfer ownership")
    try:
        await TenantService(session).transfer_ownership(
            tenant_id=tenant_id,
            current_owner_id=principal.user_id,
            new_owner_id=payload.new_owner_user_id,
        )
    except TenantAdministrationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await _audit(
        session,
        action="tenant.ownership.transferred",
        actor_user_id=principal.user_id,
        tenant_id=tenant_id,
        metadata={"new_owner_user_id": payload.new_owner_user_id},
    )
    member = next(
        (item for item in await TenantService(session).list_members(tenant_id) if item.user_id == payload.new_owner_user_id),
        None,
    )
    if member is None:
        raise HTTPException(status_code=404, detail="new owner was not found")
    return TenantMemberResponse(
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        role=member.role,
        username=member.username,
        email=member.email,
    )


@router.delete("/members/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    target_user_id: int,
    tenant_id: Annotated[UUID, Depends(get_current_tenant_id)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    membership = await authorization.require_permission(
        user_id=principal.user_id, tenant_id=tenant_id, permission=Permission.MEMBERS_MANAGE
    )
    if target_user_id == principal.user_id and membership.role == TenantRole.OWNER:
        raise HTTPException(status_code=403, detail="owner must transfer ownership before leaving")
    try:
        await TenantService(session).remove_member(
            tenant_id=tenant_id, target_user_id=target_user_id, actor_role=membership.role
        )
    except TenantAdministrationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await _audit(
        session,
        action="tenant.member.removed",
        actor_user_id=principal.user_id,
        tenant_id=tenant_id,
        metadata={"target_user_id": target_user_id},
    )
