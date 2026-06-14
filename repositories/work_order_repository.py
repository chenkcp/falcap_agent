from typing import Any, Dict, List
from infrastructure.query_service import DataQueryService

# ============================================================
# 5. Work-order data access
# ============================================================

class WorkOrderRepository:
    def __init__(self, query_service: DataQueryService):
        self.qs = query_service

    def check_work_order_ready(self, wo: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            WOD.work_order_id,
            WOD.work_order_status_nm,
            WOD.work_order_open_dm,
            WOD.work_order_start_dm,
            WOD.work_order_close_dm,
            WOD.on_hold_fg,
            WOD.comment_tx,
            WOD.inv_item_dim_ky,
            WOD.work_order_dest_nm,
            WOD.prod_family_nm,
            WOD.prod_family_dim_ky,
            WOD.run_type_dim_ky
        FROM RPTDS.WORK_ORDER_DIM WOD
        JOIN RPTDS.INV_ITEM_DIM IID
            ON IID.INV_ITEM_DIM_KY = WOD.INV_ITEM_DIM_KY
        WHERE WOD.WORK_ORDER_STATUS_NM = 'Closed'
          AND WOD.WORK_ORDER_DEST_NM = 'FGI'
          AND WOD.UPDATE_DM > current_date - 270
          AND IID.PART_TYPE_NM NOT IN ('DRY PEN', 'PEN BODY')
          AND WOD.INV_ITEM_DIM_KY NOT IN (
              '240540','462037','499139','470401','520140','537036',
              '568836','649026','692348','727567','892317','763773'
          )
          AND WOD.WORK_ORDER_ID = :wo
        """
        return self.qs.run_query(sql, {"wo": wo})

    def get_work_order_pens(self, wo: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT *
        FROM falcon.pen_work_order
        WHERE work_order_id = :wo
        """
        return self.qs.run_query(sql, {"wo": wo})

    def check_wo_result_exists(self, wo: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT *
        FROM rptds.fceolqt_wo_result_fact
        WHERE work_order_id = :wo
        """
        return self.qs.run_query(sql, {"wo": wo})

    def get_pen_info(self, wo: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            pn_id,
            arch_id,
            odd_ink_color_nm,
            odd_ink_type_nm,
            even_ink_color_nm,
            even_ink_type_nm,
            mfg_inkfill_start_dm,
            mfg_inkfill_end_dm
        FROM rptds.pen_info_dim
        WHERE last_affect_yld_work_order_id = :wo
        """
        return self.qs.run_query(sql, {"wo": wo})

    def get_wafer_info(self, wo: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            pn_id,
            invitemlk1_id as wafer_lot_id,
            invitemlk2_id as wafer_id,
            invitemlk3_id as die_row_nr,
            invitemlk4_id as die_col_nr
        FROM falcon.pen_link_component
        WHERE invitemlk_ky ='100' AND pn_id in (select distinct pn_id from rptds.pen_info_dim where last_affect_yld_work_order_id = :wo)
        """
        return self.qs.run_query(sql, {"wo": wo})
    
    def get_clouseau_rows(self, wo: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT *
        FROM falcon.cl_main
        WHERE test_req_id = :wo
          AND test_pen_id IN (
              SELECT DISTINCT pn_id
              FROM rptds.pen_info_dim
              WHERE last_affect_yld_work_order_id = :wo
          )
        """
        return self.qs.run_query(sql, {"wo": wo})

    def get_hueminator_rows(self, wo: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT *
        FROM falcon.sample_analysis
        WHERE job_id = :wo
          AND sample_id IN (
              SELECT DISTINCT pn_id
              FROM rptds.pen_info_dim
              WHERE last_affect_yld_work_order_id = :wo
          )
        """
        return self.qs.run_query(sql, {"wo": wo})

    def get_process_step_rows(self, wo: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT *
        FROM rptds.pen_process_fact
        WHERE pn_id IN (
            SELECT pn_id
            FROM falcon.pen_work_order
            WHERE work_order_id = :wo
        )
        AND process_step_dim_ky IN (2129, 2130)
        """
        return self.qs.run_query(sql, {"wo": wo})

    def derive_ink_type(self, wo: str) -> List[Dict[str, Any]]:
        sql = """
        WITH processed_pens AS (
            SELECT
                CASE
                    WHEN odd_ink_color_nm = 'TRANSPARENT DETAILING AGENT'
                        THEN even_ink_type_nm
                    WHEN even_ink_color_nm = 'TRANSPARENT DETAILING AGENT'
                        THEN odd_ink_type_nm
                    WHEN even_ink_color_nm <> 'TRANSPARENT DETAILING AGENT'
                     AND odd_ink_color_nm <> 'TRANSPARENT DETAILING AGENT'
                     AND even_ink_color_nm = odd_ink_color_nm
                        THEN odd_ink_type_nm
                    WHEN even_ink_color_nm <> 'TRANSPARENT DETAILING AGENT'
                     AND odd_ink_color_nm <> 'TRANSPARENT DETAILING AGENT'
                     AND even_ink_color_nm <> odd_ink_color_nm
                        THEN odd_ink_type_nm || '-' || even_ink_type_nm
                END AS ink_dm,
                *
            FROM rptds.pen_info_dim
        )
        SELECT
            pp.ink_dm,
            itd.ink_type_cd,
            itd.ink_type_dim_ky,
            pp.pn_id,
            pp.arch_id,
            pp.odd_ink_color_nm,
            pp.odd_ink_type_nm,
            pp.even_ink_color_nm,
            pp.even_ink_type_nm
        FROM processed_pens pp
        JOIN rptds.ink_type_dim itd
            ON itd.ink_type_nm = pp.ink_dm 
        WHERE pp.last_affect_yld_work_order_id = :wo
        """
        return self.qs.run_query(sql, {"wo": wo})

    def get_wo_audit_type(self, arch_id: Any, ink_type_dim_ky: Any) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            fceolqt_wo_type_dim_ky,
            work_order_type_nm,
            ink_type_dim_ky,
            arch_id,
            min_pen_ct,
            days_to_process_wo_ct
        FROM rptds.fceolqt_wo_type_dim
        WHERE ink_type_dim_ky = :ink_type_dim_ky
          AND arch_id::int = :arch_id
        """
        return self.qs.run_query(
            sql,
            {
                "arch_id": int(arch_id),
                "ink_type_dim_ky": int(ink_type_dim_ky),
            },
        )

    def get_audit_constraints(self, wo_type_key: Any) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            fceolqt_wo_test_cnstr_dim_ky,
            fceolqt_test_criteria_dim_ky,
            fceolqt_wo_type_dim_ky,
            prod_color_dim_ky,
            slot_type_cd,
            constraint_centile_pct,
            constraint_upper_bound_vl,
            constraint_lower_bound_vl
        FROM rptds.fceolqt_wo_test_cnstr_dim
        WHERE fceolqt_wo_type_dim_ky = :wo_type_key
        """
        return self.qs.run_query(sql, {"wo_type_key": wo_type_key})

    def get_raw_data_requirements(self, wo_type_key: Any) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            fceolqt_test_criteria_dim_ky,
            table_nm,
            column_nm,
            test_criteria_nm
        FROM rptds.fceolqt_test_criteria_dim
        WHERE fceolqt_test_criteria_dim_ky IN (
            SELECT fceolqt_test_criteria_dim_ky
            FROM rptds.fceolqt_wo_test_cnstr_dim
            WHERE fceolqt_wo_type_dim_ky = :wo_type_key
        )
        """
        return self.qs.run_query(sql, {"wo_type_key": wo_type_key})
