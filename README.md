# vm-builder-dashboard

A lightweight web dashboard for managing virtual machines across one or more hypervisors in a homelab.

Built with FastAPI, Jinja2, PicoCSS, and vanilla JS. No frontend build step.

---

## Why use it?

`vm-builder-dashboard` is meant for small self-hosted environments where you want a simple control plane without adding a heavy management stack.

It gives you:

- a clean web UI for browsing hosts and VMs
- a central place to create, start, stop, and delete VMs
- per-VM operation history with captured output
- basic multi-user access with admin / operator / viewer roles
- mTLS support for talking securely to your `vm-builder-agent` nodes

If you already have a few machines in your lab and want one place to operate them, this project is designed to be easy to try and easy to run.

---

## Features

- **Hypervisors view** — per-host CPU, memory, disk, and VM counts
- **Virtual Machines view** — all VMs across all registered agents in one inventory
- **VM detail view** — specs, power actions, captured operation output, and destructive actions
- **Operation history** — synchronous create/delete output stored locally and shown per VM
- **Agent management** — register and remove `vm-builder-agent` nodes from the UI
- **User management** — built-in admin / operator / viewer roles with self-signup approval flow
- **Server-side sessions** — `HttpOnly` cookie auth with revocable sessions in SQLite
- **Built-in PKI** — generates a local CA and client certificate for agent mTLS
- **No frontend build pipeline** — just Python, templates, CSS, and a small amount of JS

---

## Requirements

- Python 3.11+
- One or more reachable `vm-builder-agent` instances over HTTP or HTTPS

---

## Quick Start

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

### Start the dashboard

```bash
uvicorn main:app --host 0.0.0.0 --port 8081
```

Then open the dashboard in your browser and register your agents from the `Agents` page.

---

## Running In A Homelab

For a typical homelab setup:

1. Run `vm-builder-dashboard` on a small always-on node.
2. Run `vm-builder-agent` on each hypervisor you want to manage.
3. Download or copy the generated CA certificate from the dashboard to each agent host.
4. Register each agent in the dashboard UI.

Once that is done, the dashboard becomes your central view for hosts, VMs, and day-to-day operations.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-me` | Secret used to sign session tokens — **change in production** |
| `DB_PATH` | `/var/lib/vm-builder-dashboard/db.sqlite3` | Path to the SQLite database file |
| `AGENT_PKI_DIR` | `/var/lib/vm-builder-dashboard/pki` | Directory containing the generated CA and dashboard client certificate |
| `AGENT_HEALTH_INTERVAL` | `10` | Seconds between background agent health checks |
| `AGENT_TIMEOUT_SECONDS` | `30` | Timeout for proxied agent API calls |
| `AGENT_HEALTH_TIMEOUT_SECONDS` | `5` | Timeout for background `/health` checks |
| `AGENT_TLS_INSECURE_SKIP_VERIFY` | `false` | Set to `true` to skip HTTPS certificate verification for agent calls |

On startup the app generates these files in `AGENT_PKI_DIR` if they do not already exist:

- `vm-builder-ca.key`
- `vm-builder-ca.crt`
- `vm-builder-apiserver.key`
- `vm-builder-apiserver.crt`

Distribute `AGENT_PKI_DIR/vm-builder-ca.crt` to agent hosts as the CA they should trust for the dashboard's client certificate.

The same CA cert is also served over HTTP at `/api/pki/vm-builder-ca.crt`.

---

## Further reading

See [docs/README.md](docs/README.md) for CLI usage and systemd service installation instructions.

---

## Project structure

```text
├── main.py              # FastAPI app and startup hooks
├── cli.py               # Admin CLI for user creation and password reset
├── config.py            # Env-var settings
├── auth.py              # Password hashing, session management, role deps
├── database.py          # aiosqlite async database layer
├── routers/
│   ├── api.py           # /api/* JSON endpoints
│   └── views.py         # HTML page routes
├── services/
│   ├── agents.py        # Outbound vm-builder-agent client
│   ├── health.py        # Background agent reachability tracking
│   └── pki.py           # Local CA and client certificate generation
├── templates/
│   ├── base.html        # Shell layout, sidebar, global styles
│   ├── physical.html    # Hypervisor inventory
│   ├── virtual.html     # VM inventory + create VM dialog
│   ├── vm_detail.html   # VM specs, controls, and operation history
│   ├── agents.html      # Agent inventory
│   ├── users.html       # User management
│   ├── login.html       # Login page
│   └── signup.html      # Request access page
└── static/
    └── app.js           # Shared frontend helpers
```

---

## Roles

| Role | Capabilities |
|---|---|
| `viewer` | Read-only access to all views |
| `operator` | Can start, shutdown, create, and delete VMs |
| `admin` | Full access including user management and agent registration |
