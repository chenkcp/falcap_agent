from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import AppSettings


class DbAdapter:
    """
    Low-level database adapter.

    Responsibility:
    - Create DB engine
    - Execute parameterized SQL
    - Return rows as list[dict]
    """

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.query_log: List[Dict[str, Any]] = []
        self.active_tool_name: str | None = None
        self.engine: Engine = create_engine(
            settings.db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

    def reset_query_log(self) -> None:
        self.query_log = []

    def get_query_log(self) -> List[Dict[str, Any]]:
        return [
            {
                "sql": entry["sql"],
                "params": dict(entry["params"]),
                "row_count": entry.get("row_count"),
                "tool_name": entry.get("tool_name"),
            }
            for entry in self.query_log
        ]

    def _record_query(
        self,
        sql: str,
        params: Optional[Dict[str, Any]],
        row_count: int | None = None,
    ) -> None:
        self.query_log.append(
            {
                "sql": sql.strip(),
                "params": dict(params or {}),
                "row_count": row_count,
                "tool_name": self.active_tool_name,
            }
        )

    def fetch_all(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:

        params = params or {}

        limited_sql = f"""
        {sql}
        LIMIT {self.settings.max_rows}
        """

        with self.engine.connect() as conn:
            result = conn.execute(text(limited_sql), params)
            rows = [dict(row._mapping) for row in result]
            self._record_query(limited_sql, params, len(rows))
            return rows

    def fetch_one(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:

        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def fetch_scalar(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:

        params = params or {}

        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params)
            row = result.fetchone()
            self._record_query(sql, params, 0 if row is None else 1)

            if not row:
                return None

            return row[0]