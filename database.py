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

            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                agent_name  TEXT NOT NULL,
                vm_name     TEXT NOT NULL,
                action      TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                log         TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );
        """)


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
                 AND s.expires_at > datetime('now')""",
            (token,),
        )
        return await cursor.fetchone()


async def delete_session(token: str):
    async with _connect() as db:
        await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        await db.commit()


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------

async def upsert_job(job_id: str, agent_name: str, vm_name: str, action: str,
                     status: str = "pending", log: str = None):
    async with _connect() as db:
        await db.execute(
            """INSERT INTO jobs (id, agent_name, vm_name, action, status, log)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   status     = excluded.status,
                   log        = excluded.log,
                   updated_at = datetime('now')""",
            (job_id, agent_name, vm_name, action, status, log),
        )
        await db.commit()


async def get_job(job_id: str):
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        )
        return await cursor.fetchone()


async def list_jobs(agent_name: str = None, vm_name: str = None,
                    action: str = None, status: str = None):
    clauses, params = [], []
    if agent_name:
        clauses.append("agent_name = ?"); params.append(agent_name)
    if vm_name:
        clauses.append("vm_name = ?");    params.append(vm_name)
    if action:
        clauses.append("action = ?");     params.append(action)
    if status:
        clauses.append("status = ?");     params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    async with _connect() as db:
        cursor = await db.execute(
            f"SELECT * FROM jobs {where} ORDER BY created_at DESC", params
        )
        return await cursor.fetchall()


async def list_jobs_for_vm(agent_name: str, vm_name: str):
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT * FROM jobs WHERE agent_name = ? AND vm_name = ? "
            "ORDER BY created_at DESC",
            (agent_name, vm_name),
        )
        return await cursor.fetchall()
