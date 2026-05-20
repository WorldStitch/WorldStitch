from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.group import Group
from MythosEngine.models.user import User
from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user, require_admin

router = APIRouter()


class GroupResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    owner_id: str
    members: List[str] = []
    member_roles: Dict[str, str] = {}
    vault_ids: List[str] = []
    permissions: Dict[str, bool] = {}
    is_active: bool


class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)
    description: Optional[str] = None


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=64)
    description: Optional[str] = None
    permissions: Optional[Dict[str, bool]] = None


class UpdateMembersRequest(BaseModel):
    user_id: str
    role: str = Field("player", min_length=2, max_length=32)


def _to_response(group: Group) -> GroupResponse:
    return GroupResponse(**group.model_dump())


@router.get("/", response_model=List[GroupResponse])
async def list_groups(
    vault_id: Optional[str] = Query(None),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    all_groups = ctx.storage.list_groups() if hasattr(ctx.storage, "list_groups") else []
    if vault_id:
        all_groups = [g for g in all_groups if vault_id in (g.vault_ids or [])]
    return [_to_response(g) for g in all_groups]


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    group = ctx.groups.get_group(group_id)
    if not group or not getattr(group, "is_active", True):
        raise HTTPException(status_code=404, detail="Group not found")
    is_admin = user.system_role in PLATFORM_ADMIN
    is_member = user.id in (group.members or []) or group.owner_id == user.id
    if not is_admin and not is_member:
        raise HTTPException(status_code=403, detail="Access denied")
    return _to_response(group)


@router.post("/", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: CreateGroupRequest,
    ctx: AppContext = Depends(get_ctx),
    admin: User = Depends(require_admin),
):
    group = ctx.groups.create_group(body.name, created_by=admin.id, description=body.description)
    return _to_response(group)


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    body: UpdateGroupRequest,
    ctx: AppContext = Depends(get_ctx),
    admin: User = Depends(require_admin),
):
    group = ctx.groups.get_group(group_id)
    if not group or not getattr(group, "is_active", True):
        raise HTTPException(status_code=404, detail="Group not found")
    if body.name is not None:
        group.name = body.name
    if body.description is not None:
        group.description = body.description
    if body.permissions is not None:
        group.permissions = {**group.permissions, **body.permissions}
    ctx.groups.update_group(group)
    return _to_response(group)


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    ctx: AppContext = Depends(get_ctx),
    admin: User = Depends(require_admin),
):
    group = ctx.groups.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    ctx.groups.delete_group(group_id)
    return {"deleted": True, "id": group_id}


@router.post("/{group_id}/members", response_model=GroupResponse)
async def add_member(
    group_id: str,
    body: UpdateMembersRequest,
    ctx: AppContext = Depends(get_ctx),
    admin: User = Depends(require_admin),
):
    group = ctx.groups.get_group(group_id)
    if not group or not getattr(group, "is_active", True):
        raise HTTPException(status_code=404, detail="Group not found")
    user = ctx.users.get_user(body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    role = (body.role or "").strip().lower()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group role is required",
        )
    if role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin is an account type and cannot be assigned as a group role",
        )
    if body.user_id not in group.members:
        group.members.append(body.user_id)
    group.member_roles[body.user_id] = role
    if group_id not in (user.groups or []):
        user.groups.append(group_id)
        ctx.users.update_user(user)
    ctx.groups.update_group(group)
    return _to_response(group)


@router.delete("/{group_id}/members/{user_id}", response_model=GroupResponse)
async def remove_member(
    group_id: str,
    user_id: str,
    ctx: AppContext = Depends(get_ctx),
    admin: User = Depends(require_admin),
):
    group = ctx.groups.get_group(group_id)
    if not group or not getattr(group, "is_active", True):
        raise HTTPException(status_code=404, detail="Group not found")
    group.members = [member for member in (group.members or []) if member != user_id]
    group.member_roles.pop(user_id, None)
    user = ctx.users.get_user(user_id)
    if user and group_id in (user.groups or []):
        user.groups = [item for item in user.groups if item != group_id]
        ctx.users.update_user(user)
    ctx.groups.update_group(group)
    return _to_response(group)
