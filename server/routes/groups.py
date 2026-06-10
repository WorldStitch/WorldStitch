from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from server.context import AppContext
from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user, require_admin
from server.storage import Actor
from WorldStitch.models.group import Group
from WorldStitch.models.user import User

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
    role: str = Field("member", min_length=2, max_length=32)


def _to_response(group: Group) -> GroupResponse:
    return GroupResponse(**group.model_dump())


@router.get("/", response_model=List[GroupResponse])
async def list_groups(
    vault_id: Optional[str] = Query(None),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    actor = Actor.from_user(user)
    all_groups = await ctx.storage.list_groups(actor)
    if vault_id:
        all_groups = [g for g in all_groups if vault_id in (g.vault_ids or [])]
    return [_to_response(g) for g in all_groups]


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    group = await ctx.storage.get_group_by_id(group_id)
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
    group = await ctx.storage.create_group(body.name, created_by=admin.id, description=body.description)
    return _to_response(group)


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    body: UpdateGroupRequest,
    ctx: AppContext = Depends(get_ctx),
    admin: User = Depends(require_admin),
):
    group = await ctx.storage.get_group_by_id(group_id)
    if not group or not getattr(group, "is_active", True):
        raise HTTPException(status_code=404, detail="Group not found")
    if body.name is not None:
        group.name = body.name
    if body.description is not None:
        group.description = body.description
    if body.permissions is not None:
        group.permissions = {**group.permissions, **body.permissions}
    await ctx.storage.update_group(group)
    return _to_response(group)


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    ctx: AppContext = Depends(get_ctx),
    admin: User = Depends(require_admin),
):
    group = await ctx.storage.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    await ctx.storage.delete_group(group_id)
    return {"deleted": True, "id": group_id}


@router.post("/{group_id}/members", response_model=GroupResponse)
async def add_member(
    group_id: str,
    body: UpdateMembersRequest,
    ctx: AppContext = Depends(get_ctx),
    admin: User = Depends(require_admin),
):
    group = await ctx.storage.get_group_by_id(group_id)
    if not group or not getattr(group, "is_active", True):
        raise HTTPException(status_code=404, detail="Group not found")
    member_user = await ctx.storage.get_user_by_id(body.user_id)
    if not member_user:
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
    if group_id not in (member_user.groups or []):
        member_user.groups.append(group_id)
        await ctx.storage.update_user(member_user)
    await ctx.storage.update_group(group)
    return _to_response(group)


@router.delete("/{group_id}/members/{user_id}", response_model=GroupResponse)
async def remove_member(
    group_id: str,
    user_id: str,
    ctx: AppContext = Depends(get_ctx),
    admin: User = Depends(require_admin),
):
    group = await ctx.storage.get_group_by_id(group_id)
    if not group or not getattr(group, "is_active", True):
        raise HTTPException(status_code=404, detail="Group not found")
    group.members = [member for member in (group.members or []) if member != user_id]
    group.member_roles.pop(user_id, None)
    member_user = await ctx.storage.get_user_by_id(user_id)
    if member_user and group_id in (member_user.groups or []):
        member_user.groups = [item for item in member_user.groups if item != group_id]
        await ctx.storage.update_user(member_user)
    await ctx.storage.update_group(group)
    return _to_response(group)
