# vm-builder-dashboard — Documentation

## CLI

The CLI is available by running `main.py` directly. It operates against the same database as the running server.

### Create a user

Creates a new user with the given role and an active status (no approval required). You will be prompted for a password.

```bash
python main.py create-user --username <username> --role <admin|operator|viewer>
```

**Example — create the first admin:**
```bash
python main.py create-user --username admin --role admin
```

**Example — create a read-only account:**
```bash
python main.py create-user --username alice --role viewer
```

### Reset a password

Resets the password for an existing user. You will be prompted for the new password.

```bash
python main.py reset-password --username <username>
```

**Example:**
```bash
python main.py reset-password --username admin
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

Edit `/etc/systemd/system/vm-builder-dashboard.service` to set `SECRET_KEY` and `APISERVER_URL` before starting in production.
