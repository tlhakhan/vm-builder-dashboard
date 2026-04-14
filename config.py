import os

APISERVER_URL = os.getenv("APISERVER_URL", "http://localhost:8080")
SECRET_KEY    = os.getenv("SECRET_KEY", "dev-secret-change-me")
DB_PATH       = os.getenv("DB_PATH", "/var/lib/vm-builder-dashboard/db.sqlite3")
