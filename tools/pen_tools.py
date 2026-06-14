# tools/pen_tools.py

class PenTools:

    def __init__(self, repo):
        self.repo = repo

    def get_work_order_pens(self, state):

        rows = self.repo.get_work_order_pens(
            state["work_order_id"]
        )

        state["work_order_pens"] = rows
        state["work_order_pen_count"] = len(rows)

        return state

    def get_pen_info(self, state):

        rows = self.repo.get_pen_info(
            state["work_order_id"]
        )

        state["pen_info_rows"] = rows
        state["pen_info_count"] = len(rows)

        return state
    
    def get_wafer_info(self, state):

        rows = self.repo.get_wafer_info(
            state["work_order_id"]
        )

        state["wafer_info_rows"] = rows
        state["wafer_info_count"] = len(rows)

        return state