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

        CREATE TABLE IF NOT EXISTS decision_links (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            decision_id INTEGER NOT NULL,
            link_type TEXT NOT NULL,
            target_pattern TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, decision_id, link_type, target_pattern)
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

        CREATE TABLE IF NOT EXISTS story_snapshots (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            focus_areas_json TEXT,
            major_changes_json TEXT,
            open_questions_json TEXT,
            summary_json TEXT
        );

        CREATE TABLE IF NOT EXISTS identity_drift_snapshots (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            decision_alignment_score REAL,
            architecture_cohesion_delta REAL,
            risk_concentration_index REAL,
            causes_json TEXT,
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

        CREATE TABLE IF NOT EXISTS analysis_jobs (
            id TEXT PRIMARY KEY,
            project_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            phase TEXT,
            processed INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            message TEXT,
            checkpoint_cursor INTEGER DEFAULT 0,
            checkpoint_every INTEGER DEFAULT 500,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS analysis_file_state (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            hash TEXT,
            mtime REAL,
            size_bytes INTEGER,
            last_processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            stage_mask INTEGER DEFAULT 0,
            UNIQUE(project_id, path)
        );

        CREATE TABLE IF NOT EXISTS analysis_file_insights (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            module TEXT,
            imports_json TEXT,
            complexity INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, path)
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

    # Backfill incremental state table columns for older installations.
    try:
        afs_cols = {row[1] for row in conn.execute("PRAGMA table_info(analysis_file_state)").fetchall()}
        if afs_cols:
            if "size_bytes" not in afs_cols:
                conn.execute("ALTER TABLE analysis_file_state ADD COLUMN size_bytes INTEGER")
            if "stage_mask" not in afs_cols:
                conn.execute("ALTER TABLE analysis_file_state ADD COLUMN stage_mask INTEGER DEFAULT 0")
    except Exception:
        pass

    # Backfill analysis_jobs checkpoint columns.
    try:
        job_cols = {row[1] for row in conn.execute("PRAGMA table_info(analysis_jobs)").fetchall()}
        if job_cols:
            if "checkpoint_cursor" not in job_cols:
                conn.execute("ALTER TABLE analysis_jobs ADD COLUMN checkpoint_cursor INTEGER DEFAULT 0")
            if "checkpoint_every" not in job_cols:
                conn.execute("ALTER TABLE analysis_jobs ADD COLUMN checkpoint_every INTEGER DEFAULT 500")
    except Exception:
        pass

    conn.commit()


# Brief: get_active_decisions

def get_active_decisions(project_root: str):
    """Return active human decisions for a project, robustly.

    Includes decision id and optional link patterns when available.
    Safe fallback: empty list on any error.
    """
    try:
        root = str(Path(project_root).resolve())
        conn = connect(root)
        init_schema(conn)

        row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
        if not row:
            conn.close()
            return []
        pid = int(row[0])

        rows = conn.execute(
            """
            SELECT id, title, summary, status
            FROM decisions
            WHERE project_id=? AND status IN ('accepted', 'resolved')
            ORDER BY id DESC
            """,
            (pid,),
        ).fetchall()

        out = []
        for r in rows:
            did = int(r[0])
            lrows = conn.execute(
                "SELECT link_type, target_pattern FROM decision_links WHERE project_id=? AND decision_id=? ORDER BY id DESC",
                (pid, did),
            ).fetchall()
            out.append(
                {
                    "id": did,
                    "title": r[1],
                    "summary": r[2] or "",
                    "status": r[3],
                    "links": [{"link_type": lr[0], "target_pattern": lr[1]} for lr in lrows],
                }
            )

        conn.close()
        return out
    except Exception:
        return []
