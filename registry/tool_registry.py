from tools.readiness_tools import ReadinessTools
from tools.pen_tools import PenTools
from tools.station_tools import StationTools
from tools.audit_tools import AuditTools
from tools.raw_data_tools import RawDataTools


def build_tool_registry(repo) -> dict:
    readiness = ReadinessTools(repo)
    pen = PenTools(repo)
    station = StationTools(repo)
    audit = AuditTools(repo)
    raw = RawDataTools(repo)

    return {
        "check_work_order_ready": readiness.check_work_order_ready,
        "check_wo_result_exists": readiness.check_wo_result_exists,

        "get_work_order_pens": pen.get_work_order_pens,
        "get_pen_info": pen.get_pen_info,
        "get_wafer_info": pen.get_wafer_info,

        "check_clouseau": station.check_clouseau,
        "check_hueminator": station.check_hueminator,
        "check_process_steps": station.check_process_steps,

        "derive_ink_type": audit.derive_ink_type,
        "get_wo_audit_type": audit.get_wo_audit_type,
        "get_audit_constraints": audit.get_audit_constraints,

        "get_raw_data_requirements": raw.get_raw_data_requirements,
        "check_raw_data_availability": raw.check_raw_data_availability,

        "build_final_report": _build_final_report,
    }


def _build_final_report(state: dict) -> dict:
    """
    Normalize internal runtime state keys into the flat report schema
    that format_report() and the summary section expect.
    """
    audit_rows = state.get("audit_type_rows") or []
    audit_row = audit_rows[0] if audit_rows else {}

    process_rows = state.get("process_rows") or []
    step_2129 = sum(1 for r in process_rows if r.get("process_step_dim_ky") == 2129)
    step_2130 = sum(1 for r in process_rows if r.get("process_step_dim_ky") == 2130)

    report = {
        **state,
        # flat summary keys the formatter reads
        "arch_id":              state.get("selected_arch_id"),
        "ink_type_dim_ky":      state.get("selected_ink_type_dim_ky"),
        "ink_dm":               state.get("selected_ink_dm"),
        "pen_count":            state.get("work_order_pen_count", len(state.get("work_order_pens") or [])),
        "pen_info_count":       len(state.get("pen_info_rows") or []),
        "process_step_2129_count": step_2129,
        "process_step_2130_count": step_2130,
        "fceolqt_wo_type_dim_ky": state.get("fceolqt_wo_type_dim_ky") or audit_row.get("fceolqt_wo_type_dim_ky"),
        "min_pen_ct":           audit_row.get("min_pen_ct"),
        "days_to_process_wo_ct": audit_row.get("days_to_process_wo_ct"),
        "constraint_count":     len(state.get("audit_constraints") or []),
        "raw_requirement_count": len(state.get("raw_data_requirements") or []),
        "final_status":         _derive_final_status(state),
    }

    report["final_report"] = report
    return report


def _derive_final_status(state: dict) -> str:
    explanations = state.get("explanations") or []
    if any(e.startswith("FAIL") for e in explanations):
        return "FAIL"
    if any(e.startswith("WARN") for e in explanations):
        return "WARN"
    if any(e.startswith("PASS") for e in explanations):
        return "PASS"
    return "UNKNOWN"