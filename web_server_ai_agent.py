import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app_ai_agent import bootstrap_agent
from prompts.system_prompt import SYSTEM_PROMPT


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str


class SessionState:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.last_work_order_id: str | None = None
        self.last_report: dict[str, Any] | None = None


app = FastAPI(title="Falcon WO AI Agent Browser Chat")

WEB_DIR = Path(__file__).with_name("web")
if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")

SESSIONS: dict[str, SessionState] = {}
AGENT = bootstrap_agent()


WORK_ORDER_PATTERN = re.compile(r"\b[A-Z0-9][A-Z0-9_-]{5,40}\b", re.IGNORECASE)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "arch_id": ("arch id", "arch_id", "architecture id"),
    "ink_type_dim_ky": ("ink type dim key", "ink type", "ink_type_dim_ky"),
    "ink_dm": ("ink dm", "ink", "ink_dm"),
    "pen_count": ("wo pen count", "pen count", "work order pens"),
    "pen_info_count": ("pen info count", "pen info"),
    "min_pen_ct": ("minimum pen count", "min pen count"),
    "days_to_process_wo_ct": ("days to process", "days to process wo"),
    "constraint_count": ("constraint count", "constraints"),
    "raw_requirement_count": ("raw requirement count", "raw data requirements"),
}


def _normalize_sql(sql: str) -> str:
    return "\n".join(line.rstrip() for line in sql.strip().splitlines())


def _extract_field_name(user_input: str) -> str | None:
    lowered = user_input.lower()
    for field_name, aliases in FIELD_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return field_name
    return None


def _is_explanation_request(user_input: str) -> bool:
    lowered = user_input.lower()
    return any(
        token in lowered
        for token in (
            "why",
            "null",
            "none",
            "query",
            "sql",
            "statement",
            "explain",
            "what",
            "run",
            "ran",
            "determine",
            "determin",
            "which",
        )
    )


def _resolve_report_value(report: dict[str, Any], field_name: str) -> tuple[Any, Any, str | None]:
    fallback_key = None

    if field_name == "arch_id":
        fallback_key = "selected_arch_id"
    elif field_name == "ink_type_dim_ky":
        fallback_key = "selected_ink_type_dim_ky"
    elif field_name == "ink_dm":
        fallback_key = "selected_ink_dm"

    if field_name == "pen_count":
        fallback_value = report.get("work_order_pen_count", len(report.get("work_order_pens", [])))
        return report.get("pen_count"), fallback_value, "work_order_pen_count"

    if field_name == "pen_info_count":
        fallback_value = len(report.get("pen_info_rows", []))
        return report.get("pen_info_count"), fallback_value, "pen_info_rows"

    if field_name == "constraint_count":
        fallback_value = len(report.get("audit_constraints", []))
        return report.get("constraint_count"), fallback_value, "audit_constraints"

    if field_name == "raw_requirement_count":
        fallback_value = len(report.get("raw_data_requirements", []))
        return report.get("raw_requirement_count"), fallback_value, "raw_data_requirements"

    if field_name == "min_pen_ct":
        rows = report.get("audit_type_rows", [])
        fallback_value = rows[0].get("min_pen_ct") if rows else None
        return report.get("min_pen_ct"), fallback_value, "audit_type_rows[0].min_pen_ct"

    if field_name == "days_to_process_wo_ct":
        rows = report.get("audit_type_rows", [])
        fallback_value = rows[0].get("days_to_process_wo_ct") if rows else None
        return report.get("days_to_process_wo_ct"), fallback_value, "audit_type_rows[0].days_to_process_wo_ct"

    if fallback_key is not None:
        return report.get(field_name), report.get(fallback_key), fallback_key

    return report.get(field_name), None, None


def _query_matches_field(field_name: str, sql: str) -> bool:
    lowered = sql.lower()

    if field_name == "arch_id":
        return "arch_id" in lowered
    if field_name == "ink_type_dim_ky":
        return "ink_type_dim_ky" in lowered or "ink_type_dim" in lowered
    if field_name == "ink_dm":
        return "ink_dm" in lowered or "ink_type_nm" in lowered
    if field_name == "pen_count":
        return "pen_work_order" in lowered
    if field_name == "pen_info_count":
        return "pen_info_dim" in lowered
    if field_name == "constraint_count":
        return "fceolqt_wo_test_cnstr_dim" in lowered
    if field_name == "raw_requirement_count":
        return "fceolqt_test_criteria_dim" in lowered
    if field_name in {"min_pen_ct", "days_to_process_wo_ct"}:
        return "fceolqt_wo_type_dim" in lowered

    return field_name.lower() in lowered


def _tool_matches_field(field_name: str, tool_name: str | None) -> bool:
    if tool_name is None:
        return False

    tool_map = {
        "pen_count": "get_work_order_pens",
        "pen_info_count": "get_pen_info",
        "constraint_count": "get_audit_constraints",
        "raw_requirement_count": "get_raw_data_requirements",
        "arch_id": "derive_ink_type",
        "ink_type_dim_ky": "derive_ink_type",
        "ink_dm": "derive_ink_type",
        "min_pen_ct": "get_wo_audit_type",
        "days_to_process_wo_ct": "get_wo_audit_type",
        "fceolqt_wo_type_dim_ky": "get_wo_audit_type",
    }

    return tool_map.get(field_name) == tool_name


def explain_report_value(session: SessionState, user_input: str) -> str | None:
    if not session.last_report or not _is_explanation_request(user_input):
        return None

    field_name = _extract_field_name(user_input)
    if field_name is None:
        return None

    report = session.last_report
    summary_value, fallback_value, fallback_key = _resolve_report_value(report, field_name)

    query_log = report.get("query_log", [])

    matching_queries = [
        entry
        for entry in query_log
        if _tool_matches_field(field_name, entry.get("tool_name"))
    ]

    if not matching_queries:
        matching_queries = [
            entry
            for entry in query_log
            if _query_matches_field(field_name, entry.get("sql", ""))
        ]

    if not matching_queries:
        matching_queries = report.get("query_log", [])[-3:]

    lines = [
        f"For WO `{report.get('work_order_id', session.last_work_order_id or '')}`, `{field_name}` in the summary is `{summary_value}`.",
    ]

    tool_name = None
    if field_name == "pen_count":
        tool_name = "get_work_order_pens"
    elif field_name == "pen_info_count":
        tool_name = "get_pen_info"
    elif field_name == "constraint_count":
        tool_name = "get_audit_constraints"
    elif field_name == "raw_requirement_count":
        tool_name = "get_raw_data_requirements"
    elif field_name in {"arch_id", "ink_type_dim_ky", "ink_dm"}:
        tool_name = "derive_ink_type"
    elif field_name in {"min_pen_ct", "days_to_process_wo_ct", "fceolqt_wo_type_dim_ky"}:
        tool_name = "get_wo_audit_type"

    if tool_name is not None:
        lines.append(f"The summary value is determined by the `{tool_name}` tool.")

    if fallback_key is not None:
        lines.append(
            f"The runtime also has `{fallback_key}={fallback_value}`, so this is a report-key mismatch rather than missing source data."
        )
    elif fallback_value is not None:
        lines.append(
            f"The summary key is `{summary_value}`, but the runtime-derived value is `{fallback_value}` from `{fallback_key}`."
        )
    elif summary_value is None:
        lines.append("The value is null because no fallback value was populated in the current report state.")

    lines.append("")
    lines.append("Relevant SQL statements:")

    for index, entry in enumerate(matching_queries, start=1):
        lines.append("")
        lines.append(f"{index}. Params: `{entry.get('params', {})}`")
        lines.append("```sql")
        lines.append(_normalize_sql(entry.get("sql", "")))
        lines.append("```")

    return "\n".join(lines)


def get_session(session_id: str | None) -> tuple[str, SessionState]:
    if session_id and session_id in SESSIONS:
        return session_id, SESSIONS[session_id]

    new_id = str(uuid.uuid4())
    state = SessionState()
    SESSIONS[new_id] = state
    return new_id, state


def extract_work_order_id(user_input: str, session: SessionState) -> str | None:
    """
    Extract WO from user input.

    If the user says "run again" or "continue", reuse the session's last WO.
    Adjust this regex if your WO format is stricter.
    """
    candidates = WORK_ORDER_PATTERN.findall(user_input.upper())

    ignore_words = {
        "DEBUG",
        "CHECK",
        "WORK",
        "ORDER",
        "WORK_ORDER",
        "PLEASE",
        "RUN",
        "AGAIN",
        "CONTINUE",
        "SHOW",
        "REPORT",
        "STATUS",
    }

    for value in candidates:
        if value not in ignore_words and any(ch.isdigit() for ch in value):
            return value

    return session.last_work_order_id


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "# Work Order Debug Report",
        "",
        f"WO: `{report.get('work_order_id', '')}`",
        f"Final Status: **{report.get('final_status', 'UNKNOWN')}**",
        "",
        "## Summary",
        f"- WO Pen Count: {report.get('pen_count', 0)}",
        f"- Pen Info Count: {report.get('pen_info_count', 0)}",
        f"- Clouseau Count: {report.get('clouseau_count', 0)}",
        f"- Hueminator Count: {report.get('hueminator_count', 0)}",
        f"- Process Step 2129 Count: {report.get('process_step_2129_count', 0)}",
        f"- Process Step 2130 Count: {report.get('process_step_2130_count', 0)}",
        f"- Arch ID: {report.get('arch_id')}",
        f"- Ink Type Dim Key: {report.get('ink_type_dim_ky')}",
        f"- Ink DM: {report.get('ink_dm')}",
        f"- WO Type Dim Key: {report.get('fceolqt_wo_type_dim_ky')}",
        f"- Minimum Pen Count: {report.get('min_pen_ct')}",
        f"- Days To Process WO: {report.get('days_to_process_wo_ct')}",
        f"- Constraint Count: {report.get('constraint_count', 0)}",
        f"- Raw Requirement Count: {report.get('raw_requirement_count', 0)}",
        "",
        "## Diagnosis Steps",
    ]

    for item in report.get("explanations", []):
        lines.append(f"- {item}")

    return "\n".join(lines)


# Entry point used by /api/chat
def run_agent_turn(session: SessionState, user_input: str) -> str:
    explanation = explain_report_value(session, user_input)
    if explanation is not None:
        session.messages.append({"role": "user", "content": user_input})
        session.messages.append({"role": "assistant", "content": explanation})
        return explanation

    work_order_id = extract_work_order_id(user_input, session)

    if not work_order_id:
        return (
            "Please provide a work order ID, for example: "
            "`debug WO 4HDMORG260423D1`."
        )

    session.last_work_order_id = work_order_id

    try:
        report = AGENT.run(work_order_id)
        session.last_report = report
        answer = format_report(report)
        session.messages.append({"role": "user", "content": user_input})
        session.messages.append({"role": "assistant", "content": answer})
        return answer
    except Exception as exc:
        return f"Agent execution error for WO `{work_order_id}`: {exc}"


def _ndjson_event(payload: dict[str, Any]) -> str:
    return json.dumps(payload) + "\n"


def run_agent_turn_stream(session: SessionState, user_input: str) -> Iterator[str]:
    answer = run_agent_turn(session, user_input)
    yield _ndjson_event({"type": "delta", "text": answer})


@app.get("/", response_model=None)
def index() -> FileResponse | dict[str, str]:
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Falcon WO AI Agent API is running."}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    session_id, session = get_session(req.session_id)
    answer = run_agent_turn(session, req.message)

    return ChatResponse(session_id=session_id, answer=answer)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    session_id, session = get_session(req.session_id)

    def event_stream() -> Iterator[str]:
        yield _ndjson_event({"type": "session", "session_id": session_id})
        try:
            yield from run_agent_turn_stream(session, req.message)
            yield _ndjson_event({"type": "done"})
        except Exception as exc:
            yield _ndjson_event({"type": "error", "error": str(exc)})

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
