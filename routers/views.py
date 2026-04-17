"""
HTML view routes — render Jinja2 templates.
All handlers use async def to match the aiosqlite async database layer.
"""

from pathlib import PurePosixPath
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth import hash_password, verify_password, make_session
import database
from services.agents import AgentError, AgentRecord

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Agent helper (returns raw payload or None on error)
# ---------------------------------------------------------------------------

async def _apiserver(request: Request, method: str, path: str, body: dict = None):
    try:
        if method == "GET" and path == "/agents":
            rows = await database.list_agents()
            return [
                {
                    "name": row["name"],
                    "url": row["url"],
                    **request.app.state.health_monitor.status(row["name"]),
                }
                for row in rows
            ]

        if method == "GET" and path == "/vm":
            rows = await database.list_agents()
            items = []
            for row in rows:
                agent = AgentRecord(name=row["name"], url=row["url"])
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
                items.append(item)
            return items

        parts = [part for part in path.strip("/").split("/") if part]
        if len(parts) >= 2 and parts[0] == "agents":
            row = await database.get_agent(parts[1])
            if not row:
                return None
            agent = AgentRecord(name=row["name"], url=row["url"])

            if parts[2:] == ["node"] and method == "GET":
                return await request.app.state.agent_client.get_node(agent)
            if parts[2:] == ["vm"] and method == "GET":
                return await request.app.state.agent_client.list_vms(agent)
            if len(parts) == 4 and parts[2] == "vm" and method == "GET":
                return await request.app.state.agent_client.get_vm(agent, parts[3])
    except AgentError:
        return None
    return None


def _parse_int(value):
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
    return None


def _kib_string_to_mb(value):
    parsed = _parse_int(value)
    if parsed is None:
        return None
    return parsed // 1024


def _cloud_image_filename(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = urlsplit(value).path.rstrip("/")
    if not path:
        return None
    name = PurePosixPath(path).name
    return name or None


def _normalize_vm_common(raw_vm: dict, default_agent_name: str = "") -> dict:
    """
    Normalize common VM fields into the stable shape the templates expect.
    This is shared by both lightweight VM list responses and detailed VM info.
    """
    nested = raw_vm.get("vm")
    vm_data = nested if isinstance(nested, dict) else raw_vm

    agent_name = (
        raw_vm.get("agent_name")
        or raw_vm.get("agent")
        or raw_vm.get("hypervisor")
        or vm_data.get("agent_name")
        or vm_data.get("agent")
        or default_agent_name
        or ""
    )
    vm_name = (
        vm_data.get("name")
        or vm_data.get("vm_name")
        or raw_vm.get("name")
        or raw_vm.get("vm_name")
        or ""
    )

    creation_params = raw_vm.get("creation_params") or vm_data.get("creation_params") or {}
    cloud_image_url = (
        vm_data.get("cloud_image_url")
        or raw_vm.get("cloud_image_url")
        or creation_params.get("cloud_image_url")
        or creation_params.get("image_url")
    )
    cloud_image_filename = _cloud_image_filename(cloud_image_url)

    return {
        **raw_vm,
        **vm_data,
        "agent_name": agent_name,
        "name": vm_name,
        "state": vm_data.get("state") or raw_vm.get("state") or "unknown",
        "vcpu": (
            vm_data.get("vcpu")
            or vm_data.get("vcpus")
            or creation_params.get("cpu")
            or _parse_int(vm_data.get("cpus"))
            or raw_vm.get("vcpu")
            or raw_vm.get("vcpus")
        ),
        "ram_mb": (
            vm_data.get("ram_mb")
            or vm_data.get("memory_mb")
            or (creation_params.get("memory_gib") * 1024 if creation_params.get("memory_gib") else None)
            or _kib_string_to_mb(vm_data.get("max_memory"))
            or raw_vm.get("ram_mb")
            or raw_vm.get("memory_mb")
        ),
        "used_ram_mb": _kib_string_to_mb(vm_data.get("used_memory") or raw_vm.get("used_memory")),
        "disk_gb": (
            raw_vm.get("disk_gb")
            or vm_data.get("disk_gb")
            or raw_vm.get("disk")
            or vm_data.get("disk")
            or (creation_params.get("disks_gib") or [None])[0]
        ),
        "id": vm_data.get("id") or raw_vm.get("id"),
        "uuid": vm_data.get("uuid") or raw_vm.get("uuid"),
        "persistent": vm_data.get("persistent") or raw_vm.get("persistent"),
        "autostart": vm_data.get("autostart") or raw_vm.get("autostart"),
        "cloud_image_url": cloud_image_url,
        "cloud_image_filename": cloud_image_filename,
        "creation_params": creation_params,
    }


def _normalize_aggregate_vm(raw_vm: dict, default_agent_name: str = "") -> dict:
    return _normalize_vm_common(raw_vm, default_agent_name)


def _normalize_agent(raw_agent: dict) -> dict:
    return {
        **raw_agent,
        "name": raw_agent.get("name") or raw_agent.get("agent_name") or "",
        "url": raw_agent.get("url") or "",
        "reachable": bool(raw_agent.get("reachable", False)),
        "last_seen": raw_agent.get("last_seen") or raw_agent.get("lastSeen"),
    }


def _extract_vms_from_aggregate(raw_items) -> tuple[dict, list]:
    """
    Return (agent_bucket_map, flat_vm_list) from the aggregate /vm endpoint.
    The new apiserver returns one object per agent with a nested "vms" array.
    """
    agent_buckets = {}
    flat_vms = []

    for item in raw_items or []:
        if not isinstance(item, dict):
            continue

        if isinstance(item.get("vms"), list):
            agent_name = (
                item.get("agent_name")
                or item.get("agent")
                or item.get("hypervisor")
                or ""
            )
            normalized_bucket = {
                **item,
                "agent_name": agent_name,
                "reachable": item.get("reachable", False),
                "vms": [],
            }
            for nested_vm in item.get("vms", []):
                if isinstance(nested_vm, dict):
                    normalized_vm = _normalize_aggregate_vm(nested_vm, agent_name)
                    normalized_bucket["vms"].append(normalized_vm)
                    flat_vms.append(normalized_vm)
            if agent_name:
                agent_buckets[agent_name] = normalized_bucket
            continue

        normalized_vm = _normalize_aggregate_vm(item)
        flat_vms.append(normalized_vm)

    return agent_buckets, flat_vms


def _normalize_node_stats(node: dict | None) -> dict:
    if not isinstance(node, dict):
        return {}

    cpu    = node.get("cpu")    or {}
    memory = node.get("memory") or {}
    disk   = node.get("disk")   or {}
    vms    = node.get("vms")    or {}

    def gib(value):
        if not isinstance(value, (int, float)):
            return None
        return round(value / (1024 ** 3), 1)

    def pct(used, total):
        if used is None or total is None or total == 0:
            return None
        return round(used / total * 100)

    ram_total = gib(memory.get("total_bytes"))
    ram_used  = gib(memory.get("used_bytes"))
    ram_free = gib(memory.get("free_bytes"))
    ram_available = gib(memory.get("available_bytes"))
    disk_total = gib(disk.get("total_bytes"))
    disk_used  = gib(disk.get("used_bytes"))
    disk_free = gib(disk.get("free_bytes"))

    pci_devices = []
    for raw_device in node.get("pci_devices") or []:
        if not isinstance(raw_device, dict):
            continue
        pci_devices.append(
            {
                "address": raw_device.get("address"),
                "class": raw_device.get("class"),
                "class_id": raw_device.get("class_id"),
                "vendor": raw_device.get("vendor"),
                "vendor_id": raw_device.get("vendor_id"),
                "name": raw_device.get("name"),
                "device_id": raw_device.get("device_id"),
                "sub_vendor": raw_device.get("sub_vendor"),
                "sub_device": raw_device.get("sub_device"),
                "revision": raw_device.get("revision"),
                "iommu_group": raw_device.get("iommu_group"),
                "available": raw_device.get("available"),
                "attached_to": raw_device.get("attached_to"),
            }
        )

    return {
        "cpu_total":    cpu.get("total_cores"),
        "cpu_model":    cpu.get("model_name"),
        "ram_total":    ram_total,
        "ram_used":     ram_used,
        "ram_free":     ram_free,
        "ram_available": ram_available,
        "ram_pct":      pct(ram_used, ram_total),
        "disk_total":   disk_total,
        "disk_used":    disk_used,
        "disk_free":    disk_free,
        "disk_pct":     pct(disk_used, disk_total),
        "vms_total":    vms.get("total",   0),
        "vms_running":  vms.get("running", 0),
        "hostname":     node.get("hostname"),
        "os_name":      node.get("os_name"),
        "kernel_version": node.get("kernel_version"),
        "pci_devices":  pci_devices,
    }


def _normalize_vm_detail(raw_vm: dict | None, agent_name: str = "") -> dict | None:
    if not isinstance(raw_vm, dict):
        return None

    normalized = _normalize_vm_common(raw_vm, agent_name)
    creation_params = normalized.get("creation_params") or {}
    disk_gb = normalized.get("disk_gb")
    if disk_gb is None and isinstance(raw_vm.get("disks"), list) and raw_vm.get("disks"):
        first_disk = raw_vm["disks"][0]
        if isinstance(first_disk, dict):
            disk_gb = first_disk.get("size_gb") or first_disk.get("size")

    normalized["disk_gb"] = _parse_int(disk_gb)
    return normalized


def _ssh_key_fragment(public_key: str | None) -> str:
    value = (public_key or "").strip()
    if len(value) <= 36:
        return value or "—"
    return f"{value[:24]}...{value[-12:]}"


async def _get_session(session_token: str):
    if not session_token:
        return None
    return await database.get_session(session_token)


async def _require_auth(session_token: str, next_path: str = "/"):
    """Return (user_row, redirect). If redirect is set, return it from the handler."""
    user = await _get_session(session_token)
    if not user:
        return None, RedirectResponse(f"/login?next={next_path}",
                                      status_code=status.HTTP_302_FOUND)
    return user, None


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def root(session_token: str = Cookie(default=None)):
    user = await _get_session(session_token)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    return RedirectResponse("/physical", status_code=status.HTTP_302_FOUND)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/physical",
                     session_token: str = Cookie(default=None)):
    if await _get_session(session_token):
        return RedirectResponse("/physical", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request, "login.html", {"next": "/physical", "error": None}
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request,
                       username: str = Form(...),
                       password: str = Form(...),
                       next: str = Form(default="/physical")):
    user = await database.get_user_by_username(username)
    error = None
    if not user:
        error = "Invalid username or password."
    elif user["status"] == "pending":
        error = "Your account is awaiting approval."
    elif user["status"] == "rejected":
        error = "Your account is deactivated. Please contact an administrator."
    elif not verify_password(password, user["password"]):
        error = "Invalid username or password."

    if error:
        return templates.TemplateResponse(
            request, "login.html", {"next": next, "error": error},
            status_code=400,
        )

    token = await make_session(user["id"])
    resp = RedirectResponse(next or "/physical", status_code=status.HTTP_302_FOUND)
    resp.set_cookie("session_token", token, httponly=True, samesite="lax")
    return resp


@router.get("/logout")
async def logout(session_token: str = Cookie(default=None)):
    if session_token:
        await database.delete_session(session_token)
    resp = RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie("session_token")
    return resp


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, session_token: str = Cookie(default=None)):
    if await _get_session(session_token):
        return RedirectResponse("/physical", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request, "signup.html", {"error": None, "success": False}
    )


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(request: Request,
                        username: str = Form(...),
                        password: str = Form(...),
                        confirm: str = Form(...)):
    error = None
    if password != confirm:
        error = "Passwords do not match."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif await database.get_user_by_username(username):
        error = "Username already taken."

    if error:
        return templates.TemplateResponse(
            request, "signup.html", {"error": error, "success": False},
            status_code=400,
        )

    await database.create_user(username, hash_password(password),
                               role="viewer", status="pending")
    return templates.TemplateResponse(
        request, "signup.html", {"error": None, "success": True}
    )


# ---------------------------------------------------------------------------
# Physical view
# ---------------------------------------------------------------------------

@router.get("/physical", response_class=HTMLResponse)
async def physical_view(request: Request, session_token: str = Cookie(default=None)):
    user, redir = await _require_auth(session_token, "/physical")
    if redir:
        return redir

    raw_agents = await _apiserver(request, "GET", "/agents") or []
    agents = []
    for raw in raw_agents:
        if not isinstance(raw, dict):
            continue
        agent = _normalize_agent(raw)
        if agent.get("reachable"):
            node_raw = await _apiserver(request, "GET", f"/agents/{agent['name']}/node") or {}
        else:
            node_raw = {}
        agent["node"] = _normalize_node_stats(node_raw)
        agents.append(agent)

    agents.sort(key=lambda a: a.get("name", "").lower())

    return templates.TemplateResponse(
        request, "physical.html", {"user": dict(user), "agents": agents}
    )


@router.get("/physical/{agent_name}", response_class=HTMLResponse)
async def hypervisor_detail(request: Request, agent_name: str,
                            session_token: str = Cookie(default=None)):
    user, redir = await _require_auth(session_token, f"/physical/{agent_name}")
    if redir:
        return redir

    raw_agents = await _apiserver(request, "GET", "/agents") or []
    agent = None
    for raw in raw_agents:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_agent(raw)
        if normalized.get("name") == agent_name:
            agent = normalized
            break

    if agent is None:
        return RedirectResponse("/physical", status_code=status.HTTP_302_FOUND)

    node_raw = {}
    if agent.get("reachable"):
        node_raw = await _apiserver(request, "GET", f"/agents/{agent_name}/node") or {}
    node = _normalize_node_stats(node_raw)

    return templates.TemplateResponse(
        request, "hypervisor_detail.html",
        {
            "user": dict(user),
            "agent": agent,
            "agent_name": agent_name,
            "node": node,
        },
    )


# ---------------------------------------------------------------------------
# Virtual view
# ---------------------------------------------------------------------------

@router.get("/virtual", response_class=HTMLResponse)
async def virtual_view(request: Request, session_token: str = Cookie(default=None)):
    user, redir = await _require_auth(session_token, "/virtual")
    if redir:
        return redir

    raw_agents = await _apiserver(request, "GET", "/agents") or []
    flat_vms = []

    for raw in raw_agents:
        if not isinstance(raw, dict):
            continue
        agent = _normalize_agent(raw)
        if not agent.get("reachable"):
            continue
        agent_name = agent["name"]
        raw_vms = await _apiserver(request, "GET", f"/agents/{agent_name}/vm") or []
        if not isinstance(raw_vms, list):
            raw_vms = raw_vms.get("vms") or []
        for stub in raw_vms:
            if not isinstance(stub, dict):
                continue
            vm_name = stub.get("name") or stub.get("vm_name")
            if not vm_name:
                continue
            detail = await _apiserver(request, "GET", f"/agents/{agent_name}/vm/{vm_name}") or {}
            if isinstance(detail, dict) and not detail.get("error"):
                flat_vms.append(_normalize_vm_common(detail, agent_name))
            else:
                # Fall back to stub if detail fetch failed
                flat_vms.append(_normalize_vm_common(stub, agent_name))

    flat_vms.sort(key=lambda v: (v.get("agent_name", "").lower(), v.get("name", "").lower()))

    total = len(flat_vms)
    running = sum(1 for v in flat_vms if v.get("state", "").lower() == "running")

    agents = []
    for raw in raw_agents:
        if not isinstance(raw, dict):
            continue
        agent = _normalize_agent(raw)
        node_raw = {}
        if agent.get("reachable"):
            node_raw = await _apiserver(request, "GET", f"/agents/{agent['name']}/node") or {}
        agent["node"] = _normalize_node_stats(node_raw)
        agents.append(agent)
    agents.sort(key=lambda a: a.get("name", "").lower())

    agent_pci_inventory = {}
    for agent in agents:
        if not agent.get("reachable"):
            continue
        agent_pci_inventory[agent["name"]] = [
            {
                "address": device.get("address"),
                "name": device.get("name"),
                "vendor": device.get("vendor"),
                "class": device.get("class"),
                "available": device.get("available"),
                "attached_to": device.get("attached_to"),
            }
            for device in (agent.get("node", {}).get("pci_devices") or [])
            if device.get("available")
        ]

    ssh_keys = []
    for row in await database.list_ssh_keys():
        item = dict(row)
        item["fragment"] = _ssh_key_fragment(item.get("public_key"))
        ssh_keys.append(item)

    return templates.TemplateResponse(
        request, "virtual.html",
        {
            "user": dict(user),
            "vms": flat_vms,
            "total": total,
            "running": running,
            "agents": agents,
            "agent_pci_inventory": agent_pci_inventory,
            "ssh_keys": ssh_keys,
        },
    )


# ---------------------------------------------------------------------------
# VM Detail
# ---------------------------------------------------------------------------

@router.get("/vm/{agent_name}/{vm_name}", response_class=HTMLResponse)
async def vm_detail(request: Request, agent_name: str, vm_name: str,
                    session_token: str = Cookie(default=None)):
    user, redir = await _require_auth(session_token, f"/vm/{agent_name}/{vm_name}")
    if redir:
        return redir

    vm = _normalize_vm_detail(
        await _apiserver(request, "GET", f"/agents/{agent_name}/vm/{vm_name}"),
        agent_name,
    )
    operations = await database.list_operations_for_vm(agent_name, vm_name)
    attached_pci_devices = []

    if vm:
        node_raw = await _apiserver(request, "GET", f"/agents/{agent_name}/node") or {}
        node = _normalize_node_stats(node_raw)
        attached_pci_devices = [
            device for device in (node.get("pci_devices") or [])
            if device.get("attached_to") == vm_name
        ]

    return templates.TemplateResponse(
        request, "vm_detail.html",
        {
            "user":       dict(user),
            "agent_name": agent_name,
            "vm_name":    vm_name,
            "vm":         vm,
            "operations": [dict(item) for item in operations],
            "attached_pci_devices": attached_pci_devices,
        },
    )


# ---------------------------------------------------------------------------
# Agents view
# ---------------------------------------------------------------------------

@router.get("/agents", response_class=HTMLResponse)
async def agents_view(request: Request, session_token: str = Cookie(default=None)):
    user, redir = await _require_auth(session_token, "/agents")
    if redir:
        return redir

    raw_agents = await _apiserver(request, "GET", "/agents") or []
    aggregate_vm = await _apiserver(request, "GET", "/vm") or []
    vm_buckets, _ = _extract_vms_from_aggregate(aggregate_vm)
    agents = []
    for raw_agent in raw_agents:
        if not isinstance(raw_agent, dict):
            continue
        agent = _normalize_agent(raw_agent)
        agent["vm_count"] = len(vm_buckets.get(agent["name"], {}).get("vms", []))
        agents.append(agent)

    agents.sort(key=lambda item: item.get("name", "").lower())

    return templates.TemplateResponse(
        request, "agents.html",
        {"user": dict(user), "agents": agents},
    )


# ---------------------------------------------------------------------------
# Users view (admin only)
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
async def users_view(request: Request, session_token: str = Cookie(default=None)):
    user, redir = await _require_auth(session_token, "/users")
    if redir:
        return redir
    if user["role"] != "admin":
        return RedirectResponse("/physical", status_code=status.HTTP_302_FOUND)

    active_users = await database.list_users(status="active")
    pending_users = await database.list_users(status="pending")
    deactivated_users = await database.list_users(status="rejected")

    return templates.TemplateResponse(
        request, "users.html",
        {
            "user": dict(user),
            "active_users": [dict(u) for u in active_users],
            "pending_users": [dict(u) for u in pending_users],
            "deactivated_users": [dict(u) for u in deactivated_users],
        },
    )


@router.get("/keys", response_class=HTMLResponse)
async def keys_view(request: Request, session_token: str = Cookie(default=None)):
    user, redir = await _require_auth(session_token, "/keys")
    if redir:
        return redir

    keys = []
    for row in await database.list_ssh_keys():
        item = dict(row)
        item["fragment"] = _ssh_key_fragment(item.get("public_key"))
        keys.append(item)

    return templates.TemplateResponse(
        request, "keys.html",
        {
            "user": dict(user),
            "keys": keys,
        },
    )
