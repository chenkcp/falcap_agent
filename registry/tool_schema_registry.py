TOOL_SCHEMA_REGISTRY = {
    "check_work_order_ready": {
        "description": "Check whether WO is Closed, FGI, recent, valid part type, and not excluded.",
        "input": {"work_order_id": "string"},
        "output": {"work_order_ready": "boolean"},
    },

    "check_wo_result_exists": {
        "description": "Check whether final WO audit result exists.",
        "input": {"work_order_id": "string"},
        "output": {"wo_result_exists": "boolean"},
    },

    "get_work_order_pens": {
        "description": "Get pens linked to the WO from FALCON.PEN_WORK_ORDER.",
        "input": {"work_order_id": "string"},
        "output": {"work_order_pen_count": "integer"},
    },

    "get_pen_info": {
        "description": "Get pn_id, arch_id, odd/even ink color and ink type.",
        "input": {"work_order_id": "string"},
        "output": {
            "pen_info_count": "integer",
            "arch_ids": "list",
        },
    },

    "get_wafer_info": {
        "description": "Get pn_id, wafer_lot_id, wafer_id, die_row_nr, die_col_nr",
        "input": {"work_order_id": "string"},
        "output": {
            "wafer_info_count": "integer",
            "wafer_lot_id": "string",
            "wafer_id": "string",
            "die_row_nr": "string",
            "die_col_nr": "string"
        },
    },

    "check_clouseau": {
        "description": "Check Clouseau test data from FALCON.CL_MAIN.",
        "input": {"work_order_id": "string"},
        "output": {"clouseau_count": "integer"},
    },

    "check_hueminator": {
        "description": "Check Hueminator test data from FALCON.SAMPLE_ANALYSIS.",
        "input": {"work_order_id": "string"},
        "output": {"hueminator_count": "integer"},
    },

    "check_process_steps": {
        "description": "Check process steps 2129 and 2130 in RPTDS.PEN_PROCESS_FACT.",
        "input": {"work_order_id": "string"},
        "output": {
            "process_step_2129_count": "integer",
            "process_step_2130_count": "integer",
        },
    },

    "derive_ink_type": {
        "description": "Derive ink_dm and map it to RPTDS.INK_TYPE_DIM.",
        "input": {"work_order_id": "string"},
        "output": {
            "arch_id": "integer",
            "ink_type_dim_ky": "integer",
            "ink_dm": "string",
        },
    },

    "get_wo_audit_type": {
        "description": "Find audit type using arch_id and ink_type_dim_ky.",
        "input": {
            "arch_id": "integer",
            "ink_type_dim_ky": "integer",
        },
        "output": {
            "fceolqt_wo_type_dim_ky": "integer",
            "min_pen_ct": "integer",
            "days_to_process_wo_ct": "integer",
        },
    },

    "get_audit_constraints": {
        "description": "Get statistic constraints for the WO audit type.",
        "input": {"fceolqt_wo_type_dim_ky": "integer"},
        "output": {"constraint_count": "integer"},
    },

    "get_raw_data_requirements": {
        "description": "Get raw audit source table and column requirements.",
        "input": {"fceolqt_wo_type_dim_ky": "integer"},
        "output": {"raw_requirement_count": "integer"},
    },

    "check_raw_data_availability": {
        "description": "Check whether raw audit data is available for required criteria.",
        "input": {
            "work_order_id": "string",
            "raw_data_requirements": "list",
        },
        "output": {"raw_data_availability": "list"},
    },

    "build_final_report": {
        "description": "Build final WO debug report.",
        "input": {"state": "object"},
        "output": {"final_report": "object"},
    },
}


def get_allowed_tool_names() -> set[str]:
    return set(TOOL_SCHEMA_REGISTRY.keys())


def get_tool_schema(tool_name: str) -> dict:
    return TOOL_SCHEMA_REGISTRY[tool_name]