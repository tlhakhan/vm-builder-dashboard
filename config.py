import os

SECRET_KEY    = os.getenv("SECRET_KEY", "dev-secret-change-me")
DB_PATH       = os.getenv("DB_PATH", "/var/lib/vm-builder-dashboard/db.sqlite3")
AGENT_HEALTH_INTERVAL = float(os.getenv("AGENT_HEALTH_INTERVAL", "10"))
AGENT_TIMEOUT_SECONDS = float(os.getenv("AGENT_TIMEOUT_SECONDS", "30"))
AGENT_HEALTH_TIMEOUT_SECONDS = float(os.getenv("AGENT_HEALTH_TIMEOUT_SECONDS", "5"))
AGENT_PKI_DIR = os.getenv("AGENT_PKI_DIR", "/var/lib/vm-builder-dashboard/pki")
AGENT_TLS_INSECURE_SKIP_VERIFY = os.getenv("AGENT_TLS_INSECURE_SKIP_VERIFY", "false").lower() in ("1", "true", "yes")
