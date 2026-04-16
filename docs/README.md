# vm-builder-dashboard — Documentation

## CLI

The CLI is available via `cli.py`. It operates against the same database as the running server.

### Create a user

Creates a new user with the given role and an active status (no approval required). You will be prompted for a password.

```bash
python cli.py create-user --username <username> --role <admin|operator|viewer>
```

**Example — create the first admin:**
```bash
python cli.py create-user --username admin --role admin
```

**Example — create a read-only account:**
```bash
python cli.py create-user --username alice --role viewer
```

### Reset a password

Resets the password for an existing user. You will be prompted for the new password.

```bash
python cli.py reset-password --username <username>
```

**Example:**
```bash
python cli.py reset-password --username admin
```

---

## Running as a systemd service

A service unit is included at `docs/vm-builder-dashboard.service`.

```bash
# Create the system user and data directory
sudo useradd --system --no-create-home vm-builder
sudo mkdir -p /var/lib/vm-builder-dashboard
sudo chown vm-builder:vm-builder /var/lib/vm-builder-dashboard

# Deploy the app
sudo cp -r . /opt/vm-builder-dashboard
sudo python3 -m venv /opt/vm-builder-dashboard/venv
sudo /opt/vm-builder-dashboard/venv/bin/pip install -r /opt/vm-builder-dashboard/requirements.txt

# Install and start the service
sudo cp docs/vm-builder-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vm-builder-dashboard
```

Edit `/etc/systemd/system/vm-builder-dashboard.service` to set `SECRET_KEY`, `AGENT_PKI_DIR`, and any agent TLS settings before starting in production.

After startup, the generated CA certificate is available at:

```text
/api/pki/vm-builder-ca.crt
```

Use that certificate on each `vm-builder-agent` host so the agent trusts the dashboard's `vm-builder-apiserver` client certificate.
