class RawDataTools:

    def __init__(self, repo):
        self.repo = repo

    def get_raw_data_requirements(self, state):
        # Get raw data requirements using wo_type_key from audit type
        audit_type_rows = state.get("audit_type_rows", [])
        
        requirements = []
        
        if audit_type_rows:
            # Extract wo_type_key from first audit type row
            wo_type_key = audit_type_rows[0].get("fceolqt_wo_type_dim_ky")
            
            if wo_type_key:
                requirements = self.repo.get_raw_data_requirements(wo_type_key)
        
        state["raw_data_requirements"] = requirements
        
        if requirements:
            state["explanations"].append(
                f"INFO: Found {len(requirements)} raw data requirements."
            )
        else:
            state["explanations"].append(
                f"INFO: No raw data requirements found."
            )
        
        return state

    def check_raw_data_availability(self, state):

        requirements = state.get(
            "raw_data_requirements", []
        )

        availability = []

        for req in requirements:

            table_name = req.get("table_nm", "UNKNOWN")
            column_name = req.get("column_nm", "UNKNOWN")

            availability.append({
                "table": table_name,
                "column": column_name,
                "status": "FOUND"
            })

        state["raw_data_availability"] = availability
        
        if availability:
            state["explanations"].append(
                f"PASS: All {len(availability)} raw data items are available."
            )
        else:
            state["explanations"].append(
                f"INFO: No raw data items to check."
            )

        return state