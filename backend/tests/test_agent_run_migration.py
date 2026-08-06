"""AGENT-02 SQLite startup migration tests."""

import os
import sqlite3
import tempfile

from sqlite_migrations import run_sqlite_migrations


def _create_pre_agent_runtime_database(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE workspaces (
            id INTEGER PRIMARY KEY,
            name TEXT,
            owner_email TEXT,
            created_at DATETIME
        );
        CREATE TABLE agents (
            id TEXT PRIMARY KEY,
            workspace_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            max_tokens INTEGER NOT NULL DEFAULT 2000,
            api_base TEXT
        );
        CREATE TABLE chat_sessions (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
        );
        CREATE TABLE chat_messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        );
        CREATE TABLE admin_users (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL,
            hashed_password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin'
        );
        """
    )
    conn.commit()
    conn.close()


def test_agent_runtime_migration_creates_tables_constraints_and_is_idempotent():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
        db_path = handle.name
    try:
        _create_pre_agent_runtime_database(db_path)
        database_url = f"sqlite:///{db_path}"

        run_sqlite_migrations(database_url)
        run_sqlite_migrations(database_url)

        conn = sqlite3.connect(db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        run_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='agent_runs'"
        ).fetchone()[0]
        conn.close()

        assert {
            "agent_runs",
            "agent_steps",
            "tool_calls",
            "approval_requests",
        }.issubset(tables)
        assert "uq_agent_runs_workspace_idempotency" in indexes
        assert "uq_agent_steps_run_sequence" in indexes
        assert "CHECK" in run_sql.upper()
    finally:
        os.unlink(db_path)
