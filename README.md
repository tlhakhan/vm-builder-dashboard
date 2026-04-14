# vm-builder-dashboard

A lightweight web dashboard for managing homelab virtual machines. Sits in front of [vm-builder-apiserver](https://github.com/tenzin-lhakhang/vm-builder-apiserver) and provides a browser UI for inspecting hypervisors, creating and managing VMs, and tracking long-running jobs.

Built with FastAPI, Jinja2, PicoCSS, and vanilla JS. No frontend build step.

---

## Features

- **Physical view** — per-host CPU, memory, and disk utilisation with progress bars
- **Virtual view** — all VMs across all agents in one table; create VMs from the UI
- **VM detail** — specs, state controls (start / shutdown), past jobs, and delete
- **Jobs** — filterable job history with live log polling via ANSI-rendered output
- **Agents** — register and remove hypervisor agents
- **Users** — admin-managed accounts with viewer / operator / admin roles; self-signup with approval flow
- **Server-side sessions** — `HttpOnly` cookie, stored in SQLite, fully revocable

---

## Requirements

- Python 3.11+
- `vm-builder-apiserver` reachable over HTTP

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
python main.py create-user --username admin --role admin
```

---

## Running

```bash
uvicorn main:app --host 0.0.0.0 --port 8081
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `APISERVER_URL` | `http://localhost:8080` | Base URL of the vm-builder-apiserver |
| `SECRET_KEY` | `dev-secret-change-me` | Secret used to sign session tokens — **change in production** |
| `DB_PATH` | `/var/lib/vm-builder-dashboard/db.sqlite3` | Path to the SQLite database file |

---

## Further reading

See [docs/README.md](docs/README.md) for CLI usage and systemd service installation instructions.

---

## Project structure

```
├── main.py              # FastAPI app, startup, CLI helpers
├── config.py            # Env-var settings
├── auth.py              # Password hashing, session management, role deps
├── database.py          # aiosqlite async database layer
├── routers/
│   ├── api.py           # /api/* JSON endpoints (apiserver proxy + job polling)
│   └── views.py         # HTML page routes
├── templates/
│   ├── base.html        # Shell layout, sidebar, global styles
│   ├── physical.html    # Physical infrastructure table
│   ├── virtual.html     # VM list + create VM dialog
│   ├── vm_detail.html   # VM specs, controls, past jobs
│   ├── jobs.html        # Filterable job history
│   ├── job_detail.html  # Live log output for a single job
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
