"""Local JSON API for agent registry, proxying, and operation history."""

import uuid

from fastapi.responses import FileResponse
from fastapi import APIRouter, Depends, HTTPException, Request, status

from auth import get_current_user, require_role
import database
from services.agents import AgentError, AgentRecord

router = APIRouter(prefix="/api")


def _agent_record(row) -> AgentRecord:
    return AgentRecord(name=row["name"], url=row["url"])


async def _get_agent_or_404(agent_name: str) -> AgentRecord:
    row = await database.get_agent(agent_name)
    if not row:
        raise HTTPException(status_code=404, detail=f"agent not found: {agent_name}")
    return _agent_record(row)


def _raise_agent_error(exc: AgentError):
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/pki/vm-builder-ca.crt")
async def get_ca_cert(request: Request):
    ca_cert = request.app.state.agent_pki["ca_cert"]
    return FileResponse(
        ca_cert,
        media_type="application/x-pem-file",
        filename="vm-builder-ca.crt",
    )


@router.get("/health")
async def health(request: Request):
    agents = await database.list_agents()
    return {
        "agent_count": len(agents),
        "reachable_agents": request.app.state.health_monitor.reachable_count(),
    }


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@router.get("/agents")
async def list_agents(request: Request, user=Depends(get_current_user)):
    rows = await database.list_agents()
    return [
        {
            "name": row["name"],
            "url": row["url"],
            **request.app.state.health_monitor.status(row["name"]),
        }
        for row in rows
    ]


@router.post("/agents/register")
async def register_agent(request: Request, user=Depends(require_role("admin"))):
    body = await request.json()
    name = (body.get("name") or "").strip()
    url = (body.get("url") or "").strip()
    if not name or not url:
        raise HTTPException(status_code=400, detail="name and url are required")
    await database.upsert_agent(name, url)
    await request.app.state.health_monitor.refresh_agent({"name": name, "url": url})
    return {"name": name, "url": url}


@router.delete("/agents/{agent_name}")
async def remove_agent(agent_name: str, user=Depends(require_role("admin"))):
    removed = await database.delete_agent(agent_name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"agent not found: {agent_name}")
    return {"name": agent_name, "removed": True}


# ---------------------------------------------------------------------------
# VMs — aggregate
# ---------------------------------------------------------------------------

@router.get("/vm")
async def list_all_vms(request: Request, user=Depends(get_current_user)):
    rows = await database.list_agents()
    out = []
    for row in rows:
        agent = _agent_record(row)
        agent_status = request.app.state.health_monitor.status(agent.name)
        item = {"agent_name": agent.name, "reachable": agent_status["reachable"], "vms": []}
        if agent_status["reachable"]:
            try:
                raw_vms = await request.app.state.agent_client.list_vms(agent)
                item["vms"] = [
                    {
                        "agent_name": agent.name,
                        "id": vm.get("id"),
                        "name": vm.get("name"),
                        "state": vm.get("state"),
                    }
                    for vm in raw_vms
                    if isinstance(vm, dict)
                ]
            except AgentError as exc:
                item["error"] = str(exc.detail)
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# VMs — per-agent
# ---------------------------------------------------------------------------

@router.get("/agents/{agent_name}/vm")
async def list_vms(request: Request, agent_name: str, user=Depends(get_current_user)):
    agent = await _get_agent_or_404(agent_name)
    try:
        return await request.app.state.agent_client.list_vms(agent)
    except AgentError as exc:
        _raise_agent_error(exc)


@router.get("/agents/{agent_name}/vm/{vm_name}")
async def get_vm(request: Request, agent_name: str, vm_name: str, user=Depends(get_current_user)):
    agent = await _get_agent_or_404(agent_name)
    try:
        return await request.app.state.agent_client.get_vm(agent, vm_name)
    except AgentError as exc:
        _raise_agent_error(exc)


@router.post("/agents/{agent_name}/vm/create")
async def create_vm(agent_name: str, request: Request,
                    user=Depends(require_role("admin", "operator"))):
    agent = await _get_agent_or_404(agent_name)
    body = await request.json()
    try:
        result = await request.app.state.agent_client.create_vm(agent, body)
    except AgentError as exc:
        _raise_agent_error(exc)
    operation_id = uuid.uuid4().hex
    await database.create_operation(
        operation_id,
        agent_name,
        result.get("name") or body.get("name", ""),
        "create",
        log=result.get("output"),
    )
    return {**result, "operation_id": operation_id}


@router.delete("/agents/{agent_name}/vm/{vm_name}")
async def delete_vm(request: Request, agent_name: str, vm_name: str,
                    user=Depends(require_role("admin", "operator"))):
    agent = await _get_agent_or_404(agent_name)
    try:
        result = await request.app.state.agent_client.delete_vm(agent, vm_name)
    except AgentError as exc:
        _raise_agent_error(exc)
    operation_id = uuid.uuid4().hex
    await database.create_operation(
        operation_id,
        agent_name,
        result.get("name") or vm_name,
        "delete",
        log=result.get("output"),
    )
    return {**result, "operation_id": operation_id}


@router.post("/agents/{agent_name}/vm/{vm_name}/start")
async def start_vm(request: Request, agent_name: str, vm_name: str,
                   user=Depends(require_role("admin", "operator"))):
    agent = await _get_agent_or_404(agent_name)
    try:
        return await request.app.state.agent_client.start_vm(agent, vm_name)
    except AgentError as exc:
        _raise_agent_error(exc)


@router.post("/agents/{agent_name}/vm/{vm_name}/shutdown")
async def shutdown_vm(request: Request, agent_name: str, vm_name: str,
                      user=Depends(require_role("admin", "operator"))):
    agent = await _get_agent_or_404(agent_name)
    try:
        return await request.app.state.agent_client.shutdown_vm(agent, vm_name)
    except AgentError as exc:
        _raise_agent_error(exc)


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

@router.get("/operations")
async def list_operations_api(agent: str = None, vm: str = None,
                              action: str = None,
                              user=Depends(get_current_user)):
    rows = await database.list_operations(agent_name=agent, vm_name=vm,
                                          action=action)
    return [dict(r) for r in rows]


@router.get("/operations/{operation_id}")
async def get_operation_api(operation_id: str, user=Depends(get_current_user)):
    row = await database.get_operation(operation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Operation not found")
    return dict(row)


# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users_api(status: str = None, user=Depends(require_role("admin"))):
    rows = await database.list_users(status=status)
    return [dict(r) for r in rows]


@router.post("/users")
async def create_user_api(request: Request, user=Depends(require_role("admin"))):
    from auth import hash_password
    body     = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    role     = body.get("role", "viewer")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    if await database.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Username already exists")
    await database.create_user(username, hash_password(password),
                               role=role, status="active")
    return {"ok": True}


@router.post("/users/{user_id}/approve")
async def approve_user_api(user_id: int, request: Request,
                            user=Depends(require_role("admin"))):
    body = await request.json()
    role = body.get("role", "viewer")
    await database.approve_user(user_id, role)
    return {"ok": True}


@router.post("/users/{user_id}/reject")
async def reject_user_api(user_id: int, user=Depends(require_role("admin"))):
    await database.reject_user(user_id)
    return {"ok": True}


@router.patch("/users/{user_id}/role")
async def update_role_api(user_id: int, request: Request,
                           user=Depends(require_role("admin"))):
    body = await request.json()
    role = body.get("role")
    if role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    await database.update_user_role(user_id, role)
    return {"ok": True}


@router.post("/users/{user_id}/deactivate")
async def deactivate_user_api(user_id: int, user=Depends(require_role("admin"))):
    await database.deactivate_user(user_id)
    return {"ok": True}
