# tools/audit_tools.py

class AuditTools:

    def __init__(self, repo):
        self.repo = repo

    def derive_ink_type(self, state):
        # Derive ink type from repository
        wo_id = state["work_order_id"]
        
        rows = self.repo.derive_ink_type(wo_id)
        
        state["ink_type_rows"] = rows
        
        # Extract arch_id and ink_type_dim_ky pairs from rows
        pairs = sorted({
            (r.get("arch_id"), r.get("ink_type_dim_ky"), r.get("ink_dm"))
            for r in rows
            if r.get("arch_id") and r.get("ink_type_dim_ky")
        })
        
        state["arch_ink_pairs"] = pairs
        
        if pairs:
            state["selected_arch_id"] = pairs[0][0]
            state["selected_ink_type_dim_ky"] = pairs[0][1]
            state["selected_ink_dm"] = pairs[0][2]
            state["explanations"].append(
                f"PASS: Derived ink mapping: arch_id={pairs[0][0]}, "
                f"ink_type_dim_ky={pairs[0][1]}, ink_dm={pairs[0][2]}."
            )
        else:
            state["explanations"].append(
                "FAIL: Cannot map derived ink_dm to RPTDS.INK_TYPE_DIM."
            )
        
        return state

    def get_wo_audit_type(self, state):
        # Get audit type for work order
        arch_id = state.get("selected_arch_id")
        ink_type_dim_ky = state.get("selected_ink_type_dim_ky")
        
        if not arch_id or not ink_type_dim_ky:
            state["audit_type_rows"] = []
            state["explanations"].append(
                "SKIP: Missing arch_id or ink_type_dim_ky. Cannot find WO audit type."
            )
            return state
        
        audit_rows = self.repo.get_wo_audit_type(arch_id, ink_type_dim_ky)
        
        state["audit_type_rows"] = audit_rows
        
        if audit_rows:
            row = audit_rows[0]
            state["fceolqt_wo_type_dim_ky"] = row["fceolqt_wo_type_dim_ky"]
            state["min_pen_ct"] = row.get("min_pen_ct")
            state["days_to_process_wo_ct"] = row.get("days_to_process_wo_ct")
            state["explanations"].append(
                f"PASS: Found audit type {row['fceolqt_wo_type_dim_ky']} "
                f"(min_pen_ct={row.get('min_pen_ct')}, "
                f"days_to_process={row.get('days_to_process_wo_ct')})."
            )
        else:
            state["explanations"].append(
                "WARN: No audit type found."
            )
        
        return state

    def get_audit_constraints(self, state):
        # Get audit constraints using wo_type_key from previous step
        audit_type_rows = state.get("audit_type_rows", [])
        
        constraints = []
        
        if audit_type_rows:
            # Extract wo_type_key from first audit type row
            wo_type_key = audit_type_rows[0].get("fceolqt_wo_type_dim_ky")
            
            if wo_type_key:
                constraints = self.repo.get_audit_constraints(wo_type_key)
        
        state["audit_constraints"] = constraints
        
        if constraints:
            state["explanations"].append(
                f"INFO: Found {len(constraints)} audit constraints."
            )
        else:
            state["explanations"].append(
                f"INFO: No audit constraints found."
            )
        
        return state