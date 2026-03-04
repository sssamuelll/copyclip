import sqlite3
from pathlib import Path


# Brief: db_path

def db_path(project_root: str) -> str:
    root = Path(project_root)
    data_dir = root / ".copyclip"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "intelligence.db")


# Brief: connect

def connect(project_root: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(project_root))
    conn.row_factory = sqlite3.Row
    return conn


# Brief: init_schema

def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY,
            root_path TEXT UNIQUE NOT NULL,
            name TEXT,
            story TEXT,
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

        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            path_prefix TEXT,
            UNIQUE(project_id, name)
        );

        CREATE TABLE IF NOT EXISTS dependencies (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            from_module TEXT NOT NULL,
            to_module TEXT NOT NULL,
            edge_type TEXT DEFAULT 'import',
            UNIQUE(project_id, from_module, to_module, edge_type)
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

        CREATE TABLE IF NOT EXISTS decision_refs (
            id INTEGER PRIMARY KEY,
            decision_id INTEGER NOT NULL,
            ref_type TEXT NOT NULL,
            ref_value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS decision_history (
            id INTEGER PRIMARY KEY,
            decision_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS risks (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            area TEXT NOT NULL,
            severity TEXT NOT NULL,
            kind TEXT NOT NULL,
            rationale TEXT,
            score INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            external_id TEXT,
            title TEXT NOT NULL,
            body TEXT,
            status TEXT,
            labels TEXT,
            author TEXT,
            url TEXT,
            source TEXT DEFAULT 'github',
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(project_id, external_id, source)
        );

        CREATE TABLE IF NOT EXISTS pulls (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            external_id TEXT,
            title TEXT NOT NULL,
            body TEXT,
            status TEXT,
            merged INTEGER DEFAULT 0,
            labels TEXT,
            author TEXT,
            url TEXT,
            source TEXT DEFAULT 'github',
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(project_id, external_id, source)
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            summary_json TEXT
        );

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            kind TEXT,
            severity TEXT,
            min_score INTEGER DEFAULT 0,
            cooldown_min INTEGER DEFAULT 60,
            enabled INTEGER DEFAULT 1,
            last_triggered_at TEXT,
            UNIQUE(project_id, name)
        );

        CREATE TABLE IF NOT EXISTS alert_events (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            rule_id INTEGER,
            title TEXT NOT NULL,
            detail TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    # Lightweight migration for existing DBs created before new columns existed.
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "story" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN story TEXT")
    except Exception:
        pass

    conn.commit()


# Brief: get_active_decisions

def get_active_decisions(project_root: str):
    try:
        root = str(Path(project_root).resolve())
        db = db_path(root)
        if not Path(db).exists():
            return []
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
        if not row:
            conn.close()
            return []
        pid = row[0]
        rows = conn.execute(
            "SELECT title, summary, status FROM decisions WHERE project_id=? AND status IN ('accepted', 'resolved') ORDER BY id DESC",
            (pid,),
        ).fetchall()
        res = [dict(r) for r in rows]
        conn.close()
        return res
    except Exception:
        return []
