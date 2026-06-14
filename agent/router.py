import json
import os
from typing import Any

from registry.tool_schema_registry import get_allowed_tool_names, get_tool_schema


class Router:
    """
    Model-heuristic router.

    Instead of fixed order, this router scores all available tools against
    current state and chooses the best next action. This keeps tool selection
    dynamic while still bounded by the approved tool schema registry.
    """

    # Preferred tie-break order only, not a hard flow.
    PRIORITY_ORDER = {
        "check_work_order_ready": 100,
        "get_work_order_pens": 90,
        "check_wo_result_exists": 85,
        "get_pen_info": 80,
        "check_clouseau": 70,
        "check_hueminator": 69,
        "check_process_steps": 68,
        "derive_ink_type": 60,
        "get_wo_audit_type": 50,
        "get_audit_constraints": 40,
        "get_raw_data_requirements": 30,
        "check_raw_data_availability": 20,
        "build_final_report": 0,
    }

    def __init__(
        self,
        available_tools: list[str] | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
    ):
        tools = set(get_allowed_tool_names())
        if available_tools is not None:
            tools = tools.intersection(set(available_tools))
        self.allowed_tools = sorted(tools)
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        self.base_url = base_url or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.timeout_seconds = timeout_seconds or int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30"))

    def next_tool(self, state: dict) -> str | None:
        completed = set(state.get("completed_tools", []))
        candidates = [t for t in self.allowed_tools if t not in completed]

        if not candidates:
            return None

        # LLM plans analysis tools only. Report finalization is code-controlled.
        llm_candidates = [t for t in candidates if t != "build_final_report"]
        if llm_candidates:
            llm_choice = self._choose_with_llm(state, llm_candidates)
            if llm_choice:
                tool_name = llm_choice.get("tool_name")
                if tool_name in llm_candidates:
                    state.setdefault("routing_trace", []).append(
                        {
                            "selected_tool": tool_name,
                            "score": llm_choice.get("confidence", 0.0),
                            "rationale": llm_choice.get("reason", "LLM selected tool."),
                            "source": "llm",
                        }
                    )
                    return tool_name

        scored: list[tuple[float, int, str, str]] = []
        for tool_name in candidates:
            score, rationale = self._score_tool(tool_name, state)
            scored.append((score, self.PRIORITY_ORDER.get(tool_name, 0), tool_name, rationale))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best_score, _, best_tool, best_rationale = scored[0]

        if best_score < 0 and "build_final_report" in candidates:
            best_tool = "build_final_report"
            best_rationale = "No high-value pending analysis; finalize report."

        state.setdefault("routing_trace", []).append(
            {
                "selected_tool": best_tool,
                "score": best_score,
                "rationale": best_rationale,
                "source": "heuristic",
            }
        )

        return best_tool

    def _choose_with_llm(self, state: dict, candidates: list[str]) -> dict[str, Any] | None:
        try:
            import ollama
        except Exception:
            return None

        model_name = self._resolve_model_name(ollama)
        if not model_name:
            return None

        prompt = self._build_llm_prompt(state, candidates)

        try:
            response = ollama.chat(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a tool-routing model for a work-order diagnostic agent. "
                            "Choose exactly one next tool from the provided candidates. "
                            "Return JSON only with keys tool_name, reason, confidence. "
                            "Never choose a tool that is not in the candidate list or already completed."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0},
            )
        except Exception:
            return None

        content = self._extract_content(response)
        if not content:
            return None

        try:
            payload = json.loads(content)
        except Exception:
            payload = self._extract_json_object(content)

        if not isinstance(payload, dict):
            return None

        tool_name = payload.get("tool_name")
        if not isinstance(tool_name, str):
            return None

        return {
            "tool_name": tool_name,
            "reason": str(payload.get("reason", "")),
            "confidence": self._coerce_confidence(payload.get("confidence")),
        }

    def _resolve_model_name(self, ollama_module: Any) -> str | None:
        try:
            model_list = ollama_module.list()
        except Exception:
            return self.model_name

        installed = set()
        models = getattr(model_list, "models", None)
        if models is None and isinstance(model_list, dict):
            models = model_list.get("models", [])

        for item in models or []:
            name = getattr(item, "model", None)
            if name is None and isinstance(item, dict):
                name = item.get("model")
            if isinstance(name, str):
                installed.add(name)

        preferred_names = [
            self.model_name,
            "qwen2.5:7b",
            "phi4-mini:latest",
            "llama3:latest",
            "mistral:latest",
        ]

        for candidate in preferred_names:
            if candidate in installed:
                return candidate

        return self.model_name if installed else None

    def _build_llm_prompt(self, state: dict, candidates: list[str]) -> str:
        lines = [
            f"Work order: {state.get('work_order_id')}",
            f"Completed tools: {state.get('completed_tools', [])}",
            f"Current state keys: {sorted(state.keys())}",
            "Candidate tools:",
        ]

        for tool_name in candidates:
            schema = get_tool_schema(tool_name)
            lines.append(
                json.dumps(
                    {
                        "tool_name": tool_name,
                        "description": schema.get("description"),
                        "input": schema.get("input", {}),
                        "output": schema.get("output", {}),
                    },
                    sort_keys=True,
                )
            )

        lines.extend(
            [
                "",
                "Choose the single best next diagnostic tool that unlocks the most useful evidence.",
                "If all evidence is sufficient, choose build_final_report.",
                "Return JSON only: {\"tool_name\": string, \"reason\": string, \"confidence\": number}",
            ]
        )
        return "\n".join(lines)

    def _extract_content(self, response: Any) -> str | None:
        if isinstance(response, dict):
            message = response.get("message") or {}
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
        message = getattr(response, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, str):
                return content
        return None

    def _extract_json_object(self, content: str) -> dict[str, Any] | None:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(content[start : end + 1])
        except Exception:
            return None

    def _coerce_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except Exception:
            return 0.0
        return max(0.0, min(1.0, confidence))

    def _score_tool(self, tool_name: str, state: dict) -> tuple[float, str]:
        schema = get_tool_schema(tool_name)
        description = schema.get("description", "")

        # Hard gate: build_final_report should run last.
        if tool_name == "build_final_report":
            pending = [
                t for t in self.allowed_tools
                if t not in set(state.get("completed_tools", [])) and t != "build_final_report"
            ]
            if pending:
                return -100.0, "Pending diagnostic tools still available."
            return 1.0, "All diagnostics done; finalize report."

        # Precondition-based gating and scoring.
        if tool_name == "check_work_order_ready":
            return self._score_when_missing(state, "work_order_ready_rows", 10.0, "Need WO eligibility check.")

        if tool_name == "check_wo_result_exists":
            return self._score_when_missing(state, "wo_result_rows", 9.0, "Need WO result existence signal.")

        if tool_name == "get_work_order_pens":
            return self._score_when_missing(state, "work_order_pens", 8.5, "Need WO pen universe.")

        if tool_name == "get_pen_info":
            if "work_order_pens" not in state and "work_order_pen_count" not in state:
                return 2.0, "Can run early, but pen universe is not yet known."
            return self._score_when_missing(state, "pen_info_rows", 8.0, "Need pen attributes including arch_id.")

        if tool_name == "check_clouseau":
            if "pen_info_rows" not in state:
                return 1.0, "Can run, but best after pen info is available."
            return self._score_when_missing(state, "clouseau_rows", 7.0, "Need Clouseau evidence.")

        if tool_name == "check_hueminator":
            if "pen_info_rows" not in state:
                return 1.0, "Can run, but best after pen info is available."
            return self._score_when_missing(state, "hueminator_rows", 7.0, "Need Hueminator evidence.")

        if tool_name == "check_process_steps":
            return self._score_when_missing(state, "process_rows", 6.5, "Need process-step evidence.")

        if tool_name == "derive_ink_type":
            if "pen_info_rows" not in state:
                return -5.0, "Blocked: requires pen info context for reliable mapping."
            if state.get("selected_arch_id") and state.get("selected_ink_type_dim_ky"):
                return -2.0, "Ink mapping already derived."
            return 6.0, "Need arch_id and ink_type_dim_ky mapping."

        if tool_name == "get_wo_audit_type":
            if not state.get("selected_arch_id") or not state.get("selected_ink_type_dim_ky"):
                return -5.0, "Blocked: missing arch_id/ink_type_dim_ky."
            return self._score_when_missing(state, "audit_type_rows", 5.0, "Need WO audit type metadata.")

        if tool_name == "get_audit_constraints":
            if not state.get("fceolqt_wo_type_dim_ky") and not state.get("audit_type_rows"):
                return -5.0, "Blocked: missing WO type key."
            return self._score_when_missing(state, "audit_constraints", 4.0, "Need constraint set.")

        if tool_name == "get_raw_data_requirements":
            if not state.get("fceolqt_wo_type_dim_ky") and not state.get("audit_type_rows"):
                return -5.0, "Blocked: missing WO type key."
            return self._score_when_missing(state, "raw_data_requirements", 3.5, "Need raw data criteria.")

        if tool_name == "check_raw_data_availability":
            if "raw_data_requirements" not in state:
                return -5.0, "Blocked: no raw data requirements loaded."
            return self._score_when_missing(state, "raw_data_availability", 3.0, "Need raw data availability verdict.")

        # Unknown future tool fallback uses schema description only.
        return 0.5, f"Heuristic fallback from schema: {description}"

    def _score_when_missing(self, state: dict, key: str, base_score: float, rationale: str) -> tuple[float, str]:
        if key in state:
            return -1.0, f"Already populated: {key}."
        return base_score, rationale

    def review_final_report(self, state: dict) -> dict[str, Any] | None:
        """
        Let the model review the generated final report and request one more
        pending analysis tool if report quality appears incomplete.
        """
        completed = set(state.get("completed_tools", []))
        pending = [
            t for t in self.allowed_tools
            if t not in completed and t != "build_final_report"
        ]

        if not pending:
            return None

        # Lightweight deterministic check first.
        report = state.get("final_report", {}) or {}
        if report.get("pen_count", 0) == 0 and "get_work_order_pens" in pending:
            return {
                "tool_name": "get_work_order_pens",
                "reason": "Report shows pen_count=0; retrieve pen universe before finalizing.",
                "confidence": 1.0,
                "source": "heuristic_report_review",
            }

        # LLM review fallback.
        llm_choice = self._choose_with_llm_for_report_review(state, pending)
        if not llm_choice:
            return None

        tool_name = llm_choice.get("tool_name")
        if tool_name not in pending:
            return None

        return {
            "tool_name": tool_name,
            "reason": llm_choice.get("reason", "LLM requested additional evidence before finalization."),
            "confidence": llm_choice.get("confidence", 0.0),
            "source": "llm_report_review",
        }

    def _choose_with_llm_for_report_review(self, state: dict, pending: list[str]) -> dict[str, Any] | None:
        try:
            import ollama
        except Exception:
            return None

        model_name = self._resolve_model_name(ollama)
        if not model_name:
            return None

        report = state.get("final_report", {}) or {}
        compact_report = {
            "work_order_id": report.get("work_order_id"),
            "final_status": report.get("final_status"),
            "pen_count": report.get("pen_count"),
            "pen_info_count": report.get("pen_info_count"),
            "clouseau_count": report.get("clouseau_count"),
            "hueminator_count": report.get("hueminator_count"),
            "arch_id": report.get("arch_id"),
            "ink_type_dim_ky": report.get("ink_type_dim_ky"),
            "constraint_count": report.get("constraint_count"),
            "raw_requirement_count": report.get("raw_requirement_count"),
        }

        prompt_lines = [
            "Review this final report and decide if one more pending analysis tool should run before finalization.",
            "Return JSON only: {\"tool_name\": string|null, \"reason\": string, \"confidence\": number}",
            f"Completed tools: {state.get('completed_tools', [])}",
            f"Pending tools: {pending}",
            f"Report summary: {json.dumps(compact_report, sort_keys=True)}",
            "If report is sufficient, return tool_name as null.",
        ]

        try:
            response = ollama.chat(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a strict QA reviewer for tool-based diagnostics. Return JSON only.",
                    },
                    {"role": "user", "content": "\n".join(prompt_lines)},
                ],
                options={"temperature": 0},
            )
        except Exception:
            return None

        content = self._extract_content(response)
        if not content:
            return None

        try:
            payload = json.loads(content)
        except Exception:
            payload = self._extract_json_object(content)

        if not isinstance(payload, dict):
            return None

        tool_name = payload.get("tool_name")
        if tool_name is None:
            return None
        if not isinstance(tool_name, str):
            return None

        return {
            "tool_name": tool_name,
            "reason": str(payload.get("reason", "")),
            "confidence": self._coerce_confidence(payload.get("confidence")),
        }