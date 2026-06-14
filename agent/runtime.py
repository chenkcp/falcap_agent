from agent.policy import AgentPolicy
from agent.router import Router
from prompts.system_prompt import SYSTEM_PROMPT


class WorkOrderAgentRuntime:
    """
    Runtime loop:

    User gives WO
    -> Router selects tool
    -> Policy validates tool
    -> Tool runs approved SQL through repository
    -> Tool updates state
    -> Runtime continues
    -> Final report returned
    """

    def __init__(
        self,
        tool_registry: dict,
        query_log_getter=None,
        query_log_resetter=None,
        router_model: str | None = None,
        router_base_url: str | None = None,
        router_timeout_seconds: int | None = None,
    ):
        self.policy = AgentPolicy()
        self.tool_registry = tool_registry
        self.router = Router(
            available_tools=list(tool_registry.keys()),
            model_name=router_model,
            base_url=router_base_url,
            timeout_seconds=router_timeout_seconds,
        )
        self.query_log_getter = query_log_getter
        self.query_log_resetter = query_log_resetter

    def run(self, work_order_id: str) -> dict:
        if self.query_log_resetter is not None:
            self.query_log_resetter()

        wo = self.policy.validate_work_order_id(work_order_id)

        state = {
            "work_order_id": wo,
            "completed_tools": [],
            "explanations": [],
            "system_prompt": SYSTEM_PROMPT,
        }

        self.policy.validate_state(state)

        while True:
            tool_name = self.router.next_tool(state)

            if tool_name is None:
                break

            self.policy.validate_tool_name(tool_name)

            tool_fn = self.tool_registry[tool_name]
            if self.query_log_getter is not None:
                db_adapter = getattr(self.query_log_getter, "__self__", None)
                if db_adapter is not None:
                    db_adapter.active_tool_name = tool_name
            state = tool_fn(state)
            if self.query_log_getter is not None:
                db_adapter = getattr(self.query_log_getter, "__self__", None)
                if db_adapter is not None:
                    db_adapter.active_tool_name = None

            state["completed_tools"].append(tool_name)
            state.setdefault("tool_outputs", {})[tool_name] = self._capture_tool_output_snapshot(state, tool_name)

        # Optional post-final-report review: run one additional analysis tool
        # if the reviewer detects an incomplete report, then rebuild final report.
        state = self._review_and_complete_report_once(state)

        query_log = self.query_log_getter() if self.query_log_getter is not None else []
        final_report = state.get("final_report")

        if isinstance(final_report, dict):
            final_report["query_log"] = query_log
            return final_report

        state["query_log"] = query_log
        return state

    def _review_and_complete_report_once(self, state: dict) -> dict:
        if "build_final_report" not in state.get("completed_tools", []):
            return state

        review = self.router.review_final_report(state)
        if not review:
            return state

        follow_up_tool = review.get("tool_name")
        if not isinstance(follow_up_tool, str):
            return state
        if follow_up_tool in state.get("completed_tools", []):
            return state
        if follow_up_tool not in self.tool_registry:
            return state

        self.policy.validate_tool_name(follow_up_tool)

        db_adapter = getattr(self.query_log_getter, "__self__", None) if self.query_log_getter is not None else None
        if db_adapter is not None:
            db_adapter.active_tool_name = follow_up_tool

        state = self.tool_registry[follow_up_tool](state)

        if db_adapter is not None:
            db_adapter.active_tool_name = None

        state["completed_tools"].append(follow_up_tool)
        state.setdefault("tool_outputs", {})[follow_up_tool] = self._capture_tool_output_snapshot(state, follow_up_tool)
        state.setdefault("routing_trace", []).append(
            {
                "selected_tool": follow_up_tool,
                "score": review.get("confidence", 0.0),
                "rationale": review.get("reason", "Requested by report review."),
                "source": review.get("source", "report_review"),
            }
        )

        # Rebuild report after additional evidence.
        state.pop("final_report", None)
        if "build_final_report" in state["completed_tools"]:
            state["completed_tools"].remove("build_final_report")

        state = self.tool_registry["build_final_report"](state)
        state["completed_tools"].append("build_final_report")
        state.setdefault("tool_outputs", {})["build_final_report"] = self._capture_tool_output_snapshot(state, "build_final_report")

        return state

    def _capture_tool_output_snapshot(self, state: dict, tool_name: str) -> dict:
        if tool_name == "derive_ink_type":
            return {
                "selected_arch_id": state.get("selected_arch_id"),
                "selected_ink_type_dim_ky": state.get("selected_ink_type_dim_ky"),
                "selected_ink_dm": state.get("selected_ink_dm"),
            }
        if tool_name == "get_wo_audit_type":
            return {
                "fceolqt_wo_type_dim_ky": state.get("fceolqt_wo_type_dim_ky"),
                "min_pen_ct": state.get("min_pen_ct"),
                "days_to_process_wo_ct": state.get("days_to_process_wo_ct"),
            }
        if tool_name == "get_audit_constraints":
            return {"constraint_count": len(state.get("audit_constraints") or [])}
        if tool_name == "get_raw_data_requirements":
            return {"raw_requirement_count": len(state.get("raw_data_requirements") or [])}
        return {
            "keys": [key for key in state.keys() if key not in {"query_log"}],
        }
