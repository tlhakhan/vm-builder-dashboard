import asyncio
import json
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class AgentError(Exception):
    def __init__(self, status_code: int, detail: Any):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class AgentRecord:
    name: str
    url: str

class AgentClient:
    def __init__(self, ca_file: str | None = None, cert_file: str | None = None,
                 key_file: str | None = None, insecure_skip_verify: bool = False,
                 timeout: float = 30):
        self.timeout = timeout
        if insecure_skip_verify:
            self.ssl_context = ssl._create_unverified_context()
        elif ca_file:
            self.ssl_context = ssl.create_default_context(cafile=ca_file)
        else:
            self.ssl_context = ssl.create_default_context()

        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        if cert_file and key_file:
            self.ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)

    async def request_json(self, method: str, url: str, body: dict | None = None,
                           timeout: float | None = None) -> Any:
        return await asyncio.to_thread(self._request_json_sync, method, url, body, timeout)

    def _request_json_sync(self, method: str, url: str, body: dict | None,
                           timeout: float | None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout,
                                        context=self.ssl_context) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                detail = json.loads(raw)
                if isinstance(detail, dict) and "error" in detail:
                    detail = detail["error"]
            except Exception:
                detail = raw.decode(errors="replace")
            raise AgentError(exc.code, detail)
        except ssl.SSLError as exc:
            raise AgentError(502, f"agent TLS failure: {exc}")
        except urllib.error.URLError as exc:
            raise AgentError(502, f"agent unreachable: {exc.reason}")
        except TimeoutError:
            raise AgentError(504, "agent request timed out")
        except socket.timeout:
            raise AgentError(504, "agent request timed out")
        except OSError as exc:
            raise AgentError(502, f"agent connection failed: {exc}")
        except json.JSONDecodeError:
            raise AgentError(502, "invalid JSON response from agent")
        except Exception as exc:
            raise AgentError(502, f"unexpected agent client failure: {exc}")

    async def health(self, agent: AgentRecord, timeout: float) -> bool:
        try:
            await self.request_json("GET", f"{agent.url}/health", timeout=timeout)
            return True
        except Exception:
            return False

    async def list_vms(self, agent: AgentRecord) -> list[dict]:
        payload = await self.request_json("GET", f"{agent.url}/vm")
        return payload if isinstance(payload, list) else []

    async def get_vm(self, agent: AgentRecord, vm_name: str) -> dict:
        payload = await self.request_json("GET", f"{agent.url}/vm/{vm_name}")
        return payload if isinstance(payload, dict) else {}

    async def get_node(self, agent: AgentRecord) -> dict:
        payload = await self.request_json("GET", f"{agent.url}/node")
        return payload if isinstance(payload, dict) else {}

    async def create_vm(self, agent: AgentRecord, body: dict) -> dict:
        payload = await self.request_json("POST", f"{agent.url}/vm/create", body)
        if not isinstance(payload, dict) or not payload.get("name"):
            raise AgentError(502, "invalid create response from agent")
        return {
            "name": payload.get("name"),
            "output": payload.get("output", ""),
            "status": "done",
            "action": "create",
        }

    async def delete_vm(self, agent: AgentRecord, vm_name: str) -> dict:
        payload = await self.request_json("DELETE", f"{agent.url}/vm/{vm_name}")
        if not isinstance(payload, dict):
            raise AgentError(502, "invalid delete response from agent")
        return {
            "name": payload.get("name") or vm_name,
            "output": payload.get("output", ""),
            "status": "done",
            "action": "delete",
        }

    async def start_vm(self, agent: AgentRecord, vm_name: str) -> dict:
        payload = await self.request_json("POST", f"{agent.url}/vm/{vm_name}/start")
        return {
            "ok": bool(payload.get("ok", True)),
            "vm_name": payload.get("name") or vm_name,
            "action": "start",
            "message": payload.get("message", ""),
        }

    async def shutdown_vm(self, agent: AgentRecord, vm_name: str) -> dict:
        payload = await self.request_json("POST", f"{agent.url}/vm/{vm_name}/shutdown")
        return {
            "ok": bool(payload.get("ok", True)),
            "vm_name": payload.get("name") or vm_name,
            "action": "shutdown",
            "message": payload.get("message", ""),
        }
