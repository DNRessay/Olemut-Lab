import os
import ssl
import urllib.parse

import pg8000.exceptions
import pg8000.native

_conn = None


def _connect():
    u = urllib.parse.urlparse(os.environ["DATABASE_URL"])
    return pg8000.native.Connection(
        user=urllib.parse.unquote(u.username),
        password=urllib.parse.unquote(u.password or ""),
        host=u.hostname,
        port=u.port or 5432,
        database=u.path.lstrip("/"),
        ssl_context=ssl.create_default_context(),
    )


def run(sql, **params):
    """Run a query, return list of dict rows. Reuses one connection per warm container."""
    global _conn
    for attempt in (0, 1):
        try:
            if _conn is None:
                _conn = _connect()
            rows = _conn.run(sql, **params)
            cols = [c["name"] for c in (_conn.columns or [])]
            return [dict(zip(cols, r)) for r in (rows or [])]
        except (pg8000.exceptions.InterfaceError, OSError):
            _conn = None
            if attempt:
                raise


def one(sql, **params):
    rows = run(sql, **params)
    return rows[0] if rows else None
