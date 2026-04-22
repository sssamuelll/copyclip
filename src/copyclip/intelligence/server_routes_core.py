from .server_helpers import json_response, read_json_body, with_meta


def handle_health_get(handler, ctx):
    json_response(
        handler,
        with_meta(
            ctx.root,
            {
                "ok": True,
                "service": "copyclip-intelligence",
                "version": __import__("os").getenv("COPYCLIP_VERSION", "dev"),
            },
        ),
    )


def handle_settings_get(handler, ctx, conn):
    rows = conn.execute("SELECT key,value FROM config ORDER BY key").fetchall()
    json_response(handler, {r[0]: r[1] for r in rows})


def handle_settings_post(handler, ctx, conn):
    data = read_json_body(handler)
    for k, v in data.items():
        conn.execute(
            "INSERT INTO config(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (k, str(v)),
        )
    conn.commit()
    json_response(handler, {"status": "ok"})
