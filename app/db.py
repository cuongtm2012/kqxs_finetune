from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator, Optional, Union

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: Optional[ConnectionPool] = None


def init_pool(min_size: int = 1, max_size: int = 10) -> None:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
        )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    if _pool is not None:
        with _pool.connection() as conn:
            yield conn
        return
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def fetch_all(query: str, params: Optional[Union[tuple, dict]] = None) -> list:
    with get_conn() as conn:
        return conn.execute(query, params or ()).fetchall()


def fetch_one(query: str, params: Optional[Union[tuple, dict]] = None) -> Optional[dict]:
    with get_conn() as conn:
        return conn.execute(query, params or ()).fetchone()


def execute(query: str, params: Optional[Union[tuple, dict]] = None) -> None:
    with get_conn() as conn:
        conn.execute(query, params or ())
        conn.commit()


def execute_returning(query: str, params: Optional[Union[tuple, dict]] = None):
    with get_conn() as conn:
        row = conn.execute(query, params or ()).fetchone()
        conn.commit()
        return row
