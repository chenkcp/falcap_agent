from config.settings import load_settings
from infrastructure.db_adapter import DbAdapter
from infrastructure.query_service import DataQueryService
from repositories.work_order_repository import WorkOrderRepository
from registry.tool_registry import build_tool_registry
from agent.runtime import WorkOrderAgentRuntime


def bootstrap_agent() -> WorkOrderAgentRuntime:
    """
    Build the Falcon WO AI agent runtime.

    Flow:
    settings
      -> db adapter
      -> query service
      -> repository
      -> tool registry
      -> WorkOrderAgentRuntime
    """
    settings = load_settings()
    db = DbAdapter(settings)
    query_service = DataQueryService(db)
    repo = WorkOrderRepository(query_service)
    tool_registry = build_tool_registry(repo)
    return WorkOrderAgentRuntime(
        tool_registry,
        query_log_getter=db.get_query_log,
        query_log_resetter=db.reset_query_log,
        router_model=settings.llm_model,
        router_base_url=settings.llm_base_url,
        router_timeout_seconds=settings.llm_timeout_seconds,
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python app.py <WORK_ORDER_ID>")
        raise SystemExit(1)

    agent = bootstrap_agent()
    report = agent.run(sys.argv[1])
    print(report)
