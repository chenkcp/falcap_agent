# tools/readiness_tools.py

class ReadinessTools:

    def __init__(self, repo):
        self.repo = repo

    def check_work_order_ready(self, state):

        rows = self.repo.check_work_order_ready(
            state["work_order_id"]
        )

        state["work_order_ready_rows"] = rows

        if rows:
            state["explanations"].append(
                "PASS: Work order is ready."
            )
        else:
            state["explanations"].append(
                "FAIL: Work order not eligible."
            )

        return state

    def check_wo_result_exists(self, state):

        rows = self.repo.check_wo_result_exists(
            state["work_order_id"]
        )

        state["wo_result_rows"] = rows

        if rows:
            state["explanations"].append(
                "PASS: WO result exists."
            )
        else:
            state["explanations"].append(
                "WARN: WO result missing."
            )

        return state