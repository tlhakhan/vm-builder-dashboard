import argparse
import asyncio
import os
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database
from routers import api, views

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(title="vm-builder-dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(views.router)
app.include_router(api.router)


@app.on_event("startup")
async def on_startup():
    from config import DB_PATH
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    await database.init_db()


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

async def _cli_create_user(username: str, role: str):
    from config import DB_PATH
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    await database.init_db()

    existing = await database.get_user_by_username(username)
    if existing:
        print(f"Error: user '{username}' already exists.")
        sys.exit(1)

    import getpass
    password = getpass.getpass("Password: ")
    confirm  = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: passwords do not match.")
        sys.exit(1)

    from auth import hash_password
    await database.create_user(username, hash_password(password),
                               role=role, status="active")
    print(f"User '{username}' created with role '{role}'.")


async def _cli_reset_password(username: str):
    from config import DB_PATH
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    await database.init_db()

    user = await database.get_user_by_username(username)
    if not user:
        print(f"Error: user '{username}' not found.")
        sys.exit(1)

    import getpass
    password = getpass.getpass("New password: ")
    confirm  = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: passwords do not match.")
        sys.exit(1)

    from auth import hash_password
    await database.update_user_password(username, hash_password(password))
    print(f"Password for '{username}' updated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="vm-builder-dashboard CLI")
    subparsers = parser.add_subparsers(dest="command")

    p_create = subparsers.add_parser("create-user", help="Create a new user")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--role", default="admin",
                          choices=["admin", "operator", "viewer"])

    p_reset = subparsers.add_parser("reset-password", help="Reset a user's password")
    p_reset.add_argument("--username", required=True)

    args = parser.parse_args()

    if args.command == "create-user":
        asyncio.run(_cli_create_user(args.username, args.role))
    elif args.command == "reset-password":
        asyncio.run(_cli_reset_password(args.username))
    else:
        parser.print_help()
        sys.exit(1)
