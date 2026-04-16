from contextlib import asynccontextmanager

import aiosqlite
from config import DB_PATH


@asynccontextmanager
async def _connect():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db():
    async with _connect() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT UNIQUE NOT NULL,
                password    TEXT NOT NULL,
                role        TEXT NOT NULL DEFAULT 'viewer',
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token       TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                expires_at  TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS operations (
                id          TEXT PRIMARY KEY,
                agent_name  TEXT NOT NULL,
                vm_name     TEXT NOT NULL,
                action      TEXT NOT NULL,
                log         TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS agents (
                name        TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

async def get_user_by_username(username: str):
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        return await cursor.fetchone()


async def get_user_by_id(user_id: int):
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        return await cursor.fetchone()


async def create_user(username: str, password_hash: str,
                      role: str = "viewer", status: str = "pending"):
    async with _connect() as db:
        await db.execute(
            "INSERT INTO users (username, password, role, status) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, status),
        )
        await db.commit()


async def update_user_password(username: str, password_hash: str):
    async with _connect() as db:
        await db.execute(
            "UPDATE users SET password = ? WHERE username = ?",
            (password_hash, username),
        )
        await db.commit()


async def list_users(status: str = None):
    async with _connect() as db:
        if status:
            cursor = await db.execute(
                "SELECT * FROM users WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM users ORDER BY created_at DESC"
            )
        return await cursor.fetchall()


async def approve_user(user_id: int, role: str):
    async with _connect() as db:
        await db.execute(
            "UPDATE users SET status = 'active', role = ? WHERE id = ?",
            (role, user_id),
        )
        await db.commit()


async def reject_user(user_id: int):
    async with _connect() as db:
        await db.execute(
            "DELETE FROM users WHERE id = ? AND status = 'pending'", (user_id,)
        )
        await db.commit()


async def update_user_role(user_id: int, role: str):
    async with _connect() as db:
        await db.execute(
            "UPDATE users SET role = ? WHERE id = ?", (role, user_id)
        )
        await db.commit()


async def deactivate_user(user_id: int):
    async with _connect() as db:
        await db.execute(
            "UPDATE users SET status = 'rejected' WHERE id = ?", (user_id,)
        )
        await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await db.commit()


async def reactivate_user(user_id: int):
    async with _connect() as db:
        await db.execute(
            "UPDATE users SET status = 'active' WHERE id = ? AND status = 'rejected'",
            (user_id,),
        )
        await db.commit()


async def delete_user_permanently(user_id: int):
    async with _connect() as db:
        await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await db.execute(
            "DELETE FROM users WHERE id = ? AND status = 'rejected'",
            (user_id,),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

async def create_session(token: str, user_id: int):
    async with _connect() as db:
        await db.execute(
            "INSERT INTO sessions (token, user_id, expires_at) "
            "VALUES (?, ?, datetime('now', '+1 day'))",
            (token, user_id),
        )
        await db.commit()


async def get_session(token: str):
    async with _connect() as db:
        cursor = await db.execute(
            """SELECT s.*, u.username, u.role, u.status
               FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token = ?
                 AND u.status = 'active'
                 AND s.expires_at > datetime('now')""",
            (token,),
        )
        return await cursor.fetchone()


async def delete_session(token: str):
    async with _connect() as db:
        await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        await db.commit()


# ---------------------------------------------------------------------------
# Operation helpers
# ---------------------------------------------------------------------------

async def upsert_operation(operation_id: str, agent_name: str, vm_name: str, action: str,
                           log: str = None):
    async with _connect() as db:
        await db.execute(
            """INSERT INTO operations (id, agent_name, vm_name, action, log)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   log = excluded.log""",
            (operation_id, agent_name, vm_name, action, log),
        )
        await db.commit()


async def get_operation(operation_id: str):
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM operations WHERE id = ?", (operation_id,)
        )
        return await cursor.fetchone()


async def list_operations(agent_name: str = None, vm_name: str = None,
                          action: str = None):
    clauses, params = [], []
    if agent_name:
        clauses.append("agent_name = ?"); params.append(agent_name)
    if vm_name:
        clauses.append("vm_name = ?");    params.append(vm_name)
    if action:
        clauses.append("action = ?");     params.append(action)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    async with _connect() as db:
        cursor = await db.execute(
            f"SELECT * FROM operations {where} ORDER BY created_at DESC", params
        )
        return await cursor.fetchall()


async def list_operations_for_vm(agent_name: str, vm_name: str):
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM operations WHERE agent_name = ? AND vm_name = ? "
            "ORDER BY created_at DESC",
            (agent_name, vm_name),
        )
        return await cursor.fetchall()

async def create_operation(operation_id: str, agent_name: str, vm_name: str, action: str,
                           log: str = None):
    await upsert_operation(operation_id, agent_name, vm_name, action, log=log)


# ---------------------------------------------------------------------------
# Agent registry helpers
# ---------------------------------------------------------------------------

async def list_agents():
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM agents ORDER BY lower(name), created_at DESC"
        )
        return await cursor.fetchall()


async def get_agent(name: str):
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM agents WHERE name = ?", (name,)
        )
        return await cursor.fetchone()


async def upsert_agent(name: str, url: str):
    async with _connect() as db:
        await db.execute(
            """INSERT INTO agents (name, url)
               VALUES (?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   url = excluded.url,
                   updated_at = datetime('now')""",
            (name, url),
        )
        await db.commit()


async def delete_agent(name: str) -> bool:
    async with _connect() as db:
        cursor = await db.execute("DELETE FROM agents WHERE name = ?", (name,))
        await db.commit()
        return cursor.rowcount > 0
