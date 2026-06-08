import ollama
import os
import json
import re

MODEL = "qwen2.5:7b"
import psycopg
from dotenv import load_dotenv

load_dotenv()

DB_SCHEMA = """
            Allowed tables and columns:

            Table: FALCON.sample_analysis
            Columns:
            - stamp
            - sample_id
            - job_id

            Table: FALCON.CL_MAIN
            Columns:
            - stamp
            - test_pen_id
            - test_req_id

            Rules:
            - work order id maps to sample_analysis.job_id
            - work order id maps to CL_MAIN.test_req_id
            """

def get_db_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

def parse_text_tool_call(text):
    pattern = r'(?:CALL TOOL|CallCheck TOOL)\s+(\w+)\((.*?)\)'
    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    tool_name = match.group(1)
    args_text = match.group(2)

    args = {}

    for part in args_text.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            args[key.strip()] = value.strip().strip('"').strip("'")

    return {
        "name": tool_name,
        "arguments": args
    }

def validate_sql(sql: str):
    sql_clean = sql.strip().lower()

    if not sql_clean.startswith("select"):
        raise ValueError("Only SELECT statements are allowed")

    blocked = [
        "delete", "update", "insert", "drop",
        "alter", "truncate", "create", "grant"
    ]

    for word in blocked:
        if re.search(rf"\b{word}\b", sql_clean):
            raise ValueError(f"Blocked unsafe SQL keyword: {word}")

    allowed_tables = [
        "falcon.sample_analysis",
        "falcon.cl_main"
    ]

    if not any(table in sql_clean for table in allowed_tables):
        raise ValueError("SQL must query an allowed table")

    return sql

def generate_sql_from_question(question: str):
    prompt = f"""
You are a PostgreSQL SQL generator.

Return SQL only.
No explanation.
No markdown.

Schema:
{DB_SCHEMA}

Rules:
- Only generate SELECT statements.
- Use LIMIT 100 unless the user asks for a specific limit.
- Do not use DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE, CREATE.
- If user asks for distinct pen id from FALCON.sample_analysis, use sample_id.
- If user asks for distinct pen id from FALCON.CL_MAIN, use test_pen_id.

User request:
{question}
"""

    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    sql = response["message"]["content"].strip()

    sql = sql.replace("```sql", "").replace("```", "").strip()

    return validate_sql(sql)

def execute_select_sql(sql: str):
    sql = validate_sql(sql)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]

    result = []
    for row in rows:
        result.append(dict(zip(columns, row)))

    return json.dumps(result, default=str, indent=2)

def query_database_by_question(question: str):
    try:
        sql = generate_sql_from_question(question)
        result = execute_select_sql(sql)

        return f"""
GENERATED SQL:
{sql}

QUERY RESULT:
{result}
"""
    except Exception as e:
        return f"Database query failed: {str(e)}"
    

def evaluate_work_order_test_pen_counts(work_order_id: str):
    sql_hueminator = """
    SELECT COUNT(DISTINCT sample_id) AS hueminator_pen_count
    FROM FALCON.sample_analysis
    WHERE job_id = %s
    """

    sql_clouseau = """
    SELECT COUNT(DISTINCT test_pen_id) AS clouseau_pen_count
    FROM FALCON.CL_MAIN
    WHERE test_req_id = %s
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_hueminator, (work_order_id,))
            hueminator_count = cur.fetchone()[0]

            cur.execute(sql_clouseau, (work_order_id,))
            clouseau_count = cur.fetchone()[0]

    return f"""
WORK ORDER TEST PROCESS EVIDENCE
Work Order ID: {work_order_id}

Process 2130 - Hueminator Test
Source Table: FALCON.sample_analysis
Pen ID Column: sample_id
Distinct Pen Count: {hueminator_count}

Process 2129 - Clouseau Test
Source Table: FALCON.CL_MAIN
Pen ID Column: test_pen_id
Distinct Pen Count: {clouseau_count}

Business Meaning:
- The distinct pen count is evidence that this work order has gone through the Hueminator and Clouseau test processes.
- These pen counts are critical inputs for the next audit process.
- The audit calculation must verify that the minimum required pen count has been met before continuing.
"""

# =========================
# TOOLS
# =========================
def explain_work_order_process_flow(work_order_id: str):
    header = get_work_order_header(work_order_id)
    steps = get_work_order_process_steps(work_order_id)
    missing_2129 = get_work_order_2129_process(work_order_id)
    missing_2130 = get_work_order_2130_process(work_order_id)

    return f"""
WORK ORDER HEADER:
{header}

PROCESS STEPS:
{steps}

MISSING LINKS:
2129 Process:
{missing_2129}

2130 Process:
{missing_2130}
"""

def list_files(folder: str):
    if not os.path.exists(folder):
        return f"Folder not found: {folder}"

    files = os.listdir(folder)

    if not files:
        return "Folder is empty"

    return "\n".join(files)


def read_file(path: str):
    if not os.path.exists(path):
        return f"File not found: {path}"

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()[:4000]

def get_work_order_header(work_order_id: str):
    sql = """
    SELECT work_order_id,work_order_status_nm,work_order_open_dm,work_order_start_dm,work_order_close_dm,
    on_hold_fg, comment_tx, WOD.inv_item_dim_ky, work_order_dest_nm,  WOD.prod_family_nm, 
    WOD.prod_family_dim_ky,run_type_dim_ky
    FROM RPTDS.WORK_ORDER_DIM WOD, RPTDS.INV_ITEM_DIM IID 
    WHERE WOD.WORK_ORDER_STATUS_NM = 'Closed' AND WOD.WORK_ORDER_DEST_NM = 'FGI' 
    AND WOD.UPDATE_DM > current_date - 270 AND IID.INV_ITEM_DIM_KY = WOD.INV_ITEM_DIM_KY 
    AND IID.PART_TYPE_NM not in ('DRY PEN','PEN BODY') 
    AND WOD.INV_ITEM_DIM_KY NOT IN ( '240540','462037','499139','470401','520140','537036','568836','649026','692348','727567','892317' ,'763773') 
    AND WOD.WORK_ORDER_ID = %s
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (work_order_id,))
            row = cur.fetchone()

    return str(row) if row else "Work order not found"


def get_work_order_process_steps(work_order_id: str):
    sql = """
    select distinct pn_id, processlk_ky from FALCON.pen_process_eqp where pn_experiment_id =  %s
    and processlk_ky in (2129,2130)
    ORDER BY processlk_ky
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (work_order_id,))
            rows = cur.fetchall()

    return "\n".join(str(r) for r in rows) if rows else "No process steps found"


def get_work_order_2129_process(work_order_id: str):
    sql = """
    SELECT stamp, test_pen_id
    FROM FALCON.CL_MAIN WHERE TEST_REQ_ID = %s
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (work_order_id,))
            rows = cur.fetchall()

    return "\n".join(str(r) for r in rows) if rows else "No missing clouseau process found"

def get_work_order_2130_process(work_order_id: str):
    sql = """
    SELECT stamp, sample_id
    FROM FALCON.sample_analysis WHERE job_id = %s
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (work_order_id,))
            rows = cur.fetchall()

    return "\n".join(str(r) for r in rows) if rows else "No missing hueminator process found"

# =========================
# TOOL DEFINITIONS
# =========================

tools = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "Execute filesystem operation to retrieve "
                "actual files and folders from local disk"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "Folder path"
                    }
                },
                "required": ["folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read actual file contents from local disk"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path"
                    }
                },
                "required": ["path"]
            }
        }
    }
]

tools.append({
    "type": "function",
    "function": {
        "name": "explain_work_order_process_flow",
        "description": (
            "Get the complete process flow for a work order ID, "
            "including header, ordered process steps, station movement, "
            "status history, and missing expected links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "work_order_id": {
                    "type": "string",
                    "description": "Work order ID, for example WO123456"
                }
            },
            "required": ["work_order_id"]
        }
    }
})

tools.append({
    "type": "function",
    "function": {
        "name": "query_database_by_question",
        "description": (
            "Convert a natural language database question into a safe SELECT query "
            "against approved FALCON tables, execute it, and return the result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Natural language database query request"
                }
            },
            "required": ["question"]
        }
    }
})

tools.append({
    "type": "function",
    "function": {
        "name": "evaluate_work_order_test_pen_counts",
        "description": (
            "Evaluate whether a work order has evidence of Hueminator process 2130 "
            "and Clouseau process 2129 by counting distinct pen IDs from their "
            "respective source tables. These counts are needed for the next audit "
            "process evaluation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "work_order_id": {
                    "type": "string",
                    "description": "Work order ID"
                }
            },
            "required": ["work_order_id"]
        }
    }
})

available_tools = {
    "list_files": list_files,
    "read_file": read_file,
    "explain_work_order_process_flow": explain_work_order_process_flow,
    "query_database_by_question": query_database_by_question,
    "evaluate_work_order_test_pen_counts": evaluate_work_order_test_pen_counts
}

# =========================
# SYSTEM PROMPT
# =========================

SYSTEM_PROMPT = """
You are an enterprise investigation agent.

IMPORTANT RULES:
- Never explain shell commands unless explicitly asked.
- Never explain PowerShell commands unless explicitly asked.
- If a suitable tool exists, ALWAYS use the tool.
- Do NOT invent database results.
- Do NOT invent file contents.
- Only explain based on actual tool output.

FILE ANALYSIS RULES:
- For requests about source code logic, workflow, repositories, or implementation:
    1. Use analyze_python_structure first
    2. Then use read_python_code
    3. Explain based on actual source code

DATABASE SEMANTIC QUERY RULES:
- When user asks to query a table using natural language, use query_database_by_question.
- Use this for requests like:
  - query FALCON.sample_analysis and find distinct pen ids
  - find rows in FALCON.CL_MAIN for work order id
  - show sample_analysis records for job id
- Do not invent SQL results.
- Always execute the database tool before answering.

WORK ORDER TEST PROCESS RULES:
- FALCON.sample_analysis is the Hueminator test table.
- Hueminator corresponds to process key 2130.
- Hueminator pen id is sample_id.
- FALCON.CL_MAIN is the Clouseau test table.
- Clouseau corresponds to process key 2129.
- Clouseau pen id is test_pen_id.
- For work order process evidence, count distinct pen IDs.
- The distinct pen count proves whether the work order has gone through each test process.
- The pen count is required for the next audit process evaluation.
- When user asks whether a work order passed through Hueminator, Clouseau, process 2130, process 2129, or has enough pen count for audit, use evaluate_work_order_test_pen_counts.


- Never answer work-order flow questions from memory.
- Always retrieve actual database records first.

TOOL USAGE EXAMPLES:

User: List files in ./test
Assistant:
CALL TOOL list_files(folder="./test")

User: Explain the repository logic in ./repo/workorder.py
Assistant:
CALL TOOL analyze_python_structure(path="./repo/workorder.py")

User: List the process flow of work order id WO12345
Assistant:
CALL TOOL explain_work_order_process_flow(work_order_id="WO12345")
"""


messages = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT
    }
]

# =========================
# MAIN LOOP
# =========================

while True:

    user_input = input("\nUser: ")

    if user_input.lower() in ["exit", "quit"]:
        break

    messages.append({
        "role": "user",
        "content": user_input
    })

    # =========================
    # FIRST MODEL CALL
    # =========================

    response = ollama.chat(
        model=MODEL,
        messages=messages,
        tools=tools
    )

    message = response["message"]

    # =========================
    # TOOL CALL PATH
    # =========================

    if message.get("tool_calls"):

        print("\n[Tool Calls Detected]")

        messages.append(message)

        for tool_call in message["tool_calls"]:

            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"]["arguments"]

            print(f"\nExecuting Tool: {tool_name}")
            print(f"Arguments: {tool_args}")

            tool_function = available_tools.get(tool_name)

            if not tool_function:
                tool_result = f"Unknown tool: {tool_name}"
            else:
                try:
                    tool_result = tool_function(**tool_args)
                except Exception as e:
                    tool_result = f"Tool execution error: {str(e)}"

            print("\nTool Result:")
            print(tool_result)

            messages.append({
                "role": "tool",
                "content": str(tool_result)
            })

        # =========================
        # FINAL RESPONSE
        # =========================

        final_response = ollama.chat(
            model=MODEL,
            messages=messages
        )

        final_message = final_response["message"]["content"]

        print("\nAgent:")
        print(final_message)

        messages.append({
            "role": "assistant",
            "content": final_message
        })

    else:
        fake_call = parse_text_tool_call(message["content"])

        if fake_call:
            print("\n[Fallback Tool Call Detected]")

            tool_name = fake_call["name"]
            tool_args = fake_call["arguments"]

            print(f"\nExecuting Tool: {tool_name}")
            print(f"Arguments: {tool_args}")

            tool_function = available_tools.get(tool_name)

            if not tool_function:
                tool_result = f"Unknown tool: {tool_name}"
            else:
                try:
                    tool_result = tool_function(**tool_args)
                except Exception as e:
                    tool_result = f"Tool execution error: {str(e)}"

            print("\nTool Result:")
            print(tool_result)

            messages.append({
                "role": "assistant",
                "content": message["content"]
            })

            messages.append({
                "role": "tool",
                "content": str(tool_result)
            })

            final_response = ollama.chat(
                model=MODEL,
                messages=messages
            )

            final_message = final_response["message"]["content"]

            print("\nAgent:")
            print(final_message)

            messages.append({
                "role": "assistant",
                "content": final_message
            })

        else:
            print("\n[No Tool Call Detected]")
            print("\nAgent:")
            print(message["content"])
            messages.append(message)

