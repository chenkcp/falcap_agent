from typing import Any, Dict, List, Optional

from infrastructure.db_adapter import DbAdapter


class DataQueryService:
    """
    Controlled query service.

    The AI agent should call tools.
    Tools should call repositories.
    Repositories should call this query service.

    The model should not generate direct SQL.
    """

    def __init__(self, db_adapter: DbAdapter):
        self.db = db_adapter

    def run_query(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:

        return self.db.fetch_all(sql, params)

    def run_one(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:

        return self.db.fetch_one(sql, params)

    def run_scalar(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:

        return self.db.fetch_scalar(sql, params)