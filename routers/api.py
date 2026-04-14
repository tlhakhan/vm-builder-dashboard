"""
/api/* JSON routes — proxy to apiserver and expose job polling for the browser.
"""

import json
import urllib.error
import urllib.request

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status

from auth import get_current_user, require_role
from config import APISERVER_URL
import database

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Apiserver proxy helper
# ---------------------------------------------------------------------------

def _apiserver(method: str, path: str, body: dict = None):
    url = f"{APISERVER_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw.decode(errors="replace")}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw.decode(errors="replace")
        raise HTTPException(status_code=exc.code, detail=detail)
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502,
                            detail=f"Apiserver unreachable: {exc.reason}")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return _apiserver("GET", "/health")


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@router.get("/agents")
async def list_agents(user=Depends(get_current_user)):
    return _apiserver("GET", "/agents")


@router.post("/agents/register")
async def register_agent(request: Request, user=Depends(require_role("admin"))):
    body = await request.json()
    return _apiserver("POST", "/agents", body)


@router.delete("/agents/{agent_name}")
async def remove_agent(agent_name: str, user=Depends(require_role("admin"))):
    return _apiserver("DELETE", f"/agents/{agent_name}")


# ---------------------------------------------------------------------------
# VMs — aggregate
# ---------------------------------------------------------------------------

@router.get("/vm")
async def list_all_vms(user=Depends(get_current_user)):
    return _apiserver("GET", "/vm")


# ---------------------------------------------------------------------------
# VMs — per-agent
# ---------------------------------------------------------------------------

@router.get("/agents/{agent_name}/vm")
async def list_vms(agent_name: str, user=Depends(get_current_user)):
    return _apiserver("GET", f"/agents/{agent_name}/vm")


@router.get("/agents/{agent_name}/vm/{vm_name}")
async def get_vm(agent_name: str, vm_name: str, user=Depends(get_current_user)):
    return _apiserver("GET", f"/agents/{agent_name}/vm/{vm_name}")


@router.post("/agents/{agent_name}/vm/create")
async def create_vm(agent_name: str, request: Request,
                    user=Depends(require_role("admin", "operator"))):
    body = await request.json()
    result = _apiserver("POST", f"/agents/{agent_name}/vm/create", body)
    job_id = result.get("job_id")
    if job_id:
        await database.upsert_job(job_id, agent_name, body.get("name", ""), "create")
    return result


@router.delete("/agents/{agent_name}/vm/{vm_name}")
async def delete_vm(agent_name: str, vm_name: str,
                    user=Depends(require_role("admin", "operator"))):
    result = _apiserver("DELETE", f"/agents/{agent_name}/vm/{vm_name}")
    job_id = result.get("job_id")
    if job_id:
        await database.upsert_job(job_id, agent_name, vm_name, "delete")
    return result


@router.post("/agents/{agent_name}/vm/{vm_name}/start")
async def start_vm(agent_name: str, vm_name: str,
                   user=Depends(require_role("admin", "operator"))):
    return _apiserver("POST", f"/agents/{agent_name}/vm/{vm_name}/start")


@router.post("/agents/{agent_name}/vm/{vm_name}/shutdown")
async def shutdown_vm(agent_name: str, vm_name: str,
                      user=Depends(require_role("admin", "operator"))):
    return _apiserver("POST", f"/agents/{agent_name}/vm/{vm_name}/shutdown")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@router.get("/jobs")
async def list_jobs_api(agent: str = None, vm: str = None,
                        action: str = None, status: str = None,
                        user=Depends(get_current_user)):
    rows = await database.list_jobs(agent_name=agent, vm_name=vm,
                                    action=action, status=status)
    return [dict(r) for r in rows]


@router.get("/jobs/{job_id}")
async def get_job_api(job_id: str, user=Depends(get_current_user)):
    row = await database.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    extra = {}

    # If still pending/running, try to refresh from apiserver
    if row["status"] in ("pending", "running"):
        try:
            result = _apiserver("GET",
                                f"/agents/{row['agent_name']}/jobs/{job_id}")
            new_status = result.get("status", row["status"])
            new_log    = result.get("log") or result.get("output") or row["log"]
            await database.upsert_job(job_id, row["agent_name"], row["vm_name"],
                                      row["action"], new_status, new_log)
            row = await database.get_job(job_id)
            extra = {
                "start_time": result.get("start_time"),
                "end_time": result.get("end_time"),
                "error": result.get("error"),
                "error_code": result.get("error_code"),
            }
        except HTTPException:
            pass  # Return what we have

    return {**dict(row), **{k: v for k, v in extra.items() if v is not None}}


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
