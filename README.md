# vm-builder-dashboard

A lightweight web dashboard for managing homelab virtual machines. It now includes the control-plane functionality that used to live in `vm-builder-apiserver`, providing both the browser UI and the backend agent registry / proxy layer in one FastAPI app.

Built with FastAPI, Jinja2, PicoCSS, and vanilla JS. No frontend build step.

---

## Features

- **Physical view** — per-host CPU, memory, and disk utilisation with progress bars
- **Virtual view** — all VMs across all agents in one table; create VMs from the UI
- **VM detail** — specs, state controls (start / shutdown), past operation output, and delete
- **Operation history** — synchronous create/delete output captured locally and shown per VM
- **Agents** — register and remove hypervisor agents
- **Users** — admin-managed accounts with viewer / operator / admin roles; self-signup with approval flow
- **Server-side sessions** — `HttpOnly` cookie, stored in SQLite, fully revocable

---

## Requirements

- Python 3.11+
- Reachable `vm-builder-agent` instances over HTTP or HTTPS

---

## Installation

```bash
git clone https://github.com/tenzin-lhakhang/vm-builder-dashboard
cd vm-builder-dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Create the first admin user

```bash
python cli.py create-user --username admin --role admin
```

---

## Running

```bash
uvicorn main:app --host 0.0.0.0 --port 8081
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-me` | Secret used to sign session tokens — **change in production** |
| `DB_PATH` | `/var/lib/vm-builder-dashboard/db.sqlite3` | Path to the SQLite database file |
| `AGENT_PKI_DIR` | `/var/lib/vm-builder-dashboard/pki` | Directory containing the generated CA and `vm-builder-apiserver` client certificate |
| `AGENT_HEALTH_INTERVAL` | `10` | Seconds between background agent health checks |
| `AGENT_TIMEOUT_SECONDS` | `30` | Timeout for proxied agent API calls |
| `AGENT_HEALTH_TIMEOUT_SECONDS` | `5` | Timeout for background `/health` checks |
| `AGENT_TLS_INSECURE_SKIP_VERIFY` | `false` | Set to `true` to skip HTTPS certificate verification for agent calls |

On startup the app generates these files in `AGENT_PKI_DIR` if they do not already exist:

- `vm-builder-ca.key`
- `vm-builder-ca.crt`
- `vm-builder-apiserver.key`
- `vm-builder-apiserver.crt`

Distribute `AGENT_PKI_DIR/vm-builder-ca.crt` to agents as the CA they should trust for the dashboard's client certificate.

The same CA cert is also served over HTTP at `/api/pki/vm-builder-ca.crt`.

---

## Further reading

See [docs/README.md](docs/README.md) for CLI usage and systemd service installation instructions.

---

## Project structure

```
├── main.py              # FastAPI app and startup hooks
├── cli.py               # Admin CLI for user creation and password reset
├── config.py            # Env-var settings
├── auth.py              # Password hashing, session management, role deps
├── database.py          # aiosqlite async database layer
├── routers/
│   ├── api.py           # /api/* JSON endpoints (agent registry + proxy + operation history)
│   └── views.py         # HTML page routes
├── services/
│   ├── agents.py        # Outbound vm-builder-agent client and response normalization
│   ├── health.py        # Background reachability tracking for registered agents
│   └── pki.py           # Local CA and client certificate generation
├── templates/
│   ├── base.html        # Shell layout, sidebar, global styles
│   ├── physical.html    # Physical infrastructure table
│   ├── virtual.html     # VM list + create VM dialog
│   ├── vm_detail.html   # VM specs, controls, past operations
│   ├── agents.html      # Agent inventory
│   ├── users.html       # User management (admin only)
│   ├── login.html       # Login page
│   └── signup.html      # Self-signup page
└── static/
    └── app.js           # apiFetch, dialogs, tabs, inline alerts
```

---

## Roles

| Role | Capabilities |
|---|---|
| `viewer` | Read-only access to all views |
| `operator` | Can start, shutdown, create, and delete VMs |
| `admin` | Full access including user management and agent registration |
