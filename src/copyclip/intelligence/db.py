import os
import sqlite3
from pathlib import Path


def db_path(project_root: str) -> str:
    root = Path(project_root)
    data_dir = root / ".copyclip"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "intelligence.db")


def connect(project_root: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(project_root))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY,
            root_path TEXT UNIQUE NOT NULL,
            name TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            language TEXT,
            size_bytes INTEGER,
            mtime REAL,
            hash TEXT,
            UNIQUE(project_id, path)
        );

        CREATE TABLE IF NOT EXISTS commits (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            sha TEXT UNIQUE,
            author TEXT,
            date TEXT,
            message TEXT
        );

        CREATE TABLE IF NOT EXISTS file_changes (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            commit_sha TEXT,
            file_path TEXT,
            additions INTEGER,
            deletions INTEGER
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            status TEXT DEFAULT 'proposed',
            confidence REAL DEFAULT 1.0,
            source_type TEXT DEFAULT 'manual',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT
        );
        """
    )
    conn.commit()
