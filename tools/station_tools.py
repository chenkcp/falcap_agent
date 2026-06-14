# tools/station_tools.py

class StationTools:

    def __init__(self, repo):
        self.repo = repo

    def check_clouseau(self, state):

        rows = self.repo.get_clouseau_rows(
            state["work_order_id"]
        )

        state["clouseau_rows"] = rows
        state["clouseau_count"] = len(rows)

        return state

    def check_hueminator(self, state):

        rows = self.repo.get_hueminator_rows(
            state["work_order_id"]
        )

        state["hueminator_rows"] = rows
        state["hueminator_count"] = len(rows)

        return state

    def check_process_steps(self, state):

        rows = self.repo.get_process_step_rows(
            state["work_order_id"]
        )

        state["process_rows"] = rows

        return state