from registry.tool_schema_registry import get_allowed_tool_names


class AgentPolicy:
    """
    Guardrails for the Falcon WO agent.
    """

    def __init__(self):
        self.allowed_tools = get_allowed_tool_names()

    def validate_work_order_id(self, work_order_id: str) -> str:
        if not work_order_id:
            raise ValueError("work_order_id is required")

        cleaned = work_order_id.strip().upper()

        if not cleaned.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Invalid work_order_id format: {work_order_id}")

        return cleaned

    def validate_tool_name(self, tool_name: str) -> None:
        if tool_name not in self.allowed_tools:
            raise ValueError(f"Tool is not approved: {tool_name}")

    def validate_state(self, state: dict) -> None:
        if "work_order_id" not in state:
            raise ValueError("state is missing work_order_id")

        if "completed_tools" not in state:
            raise ValueError("state is missing completed_tools")

        if "explanations" not in state:
            raise ValueError("state is missing explanations")