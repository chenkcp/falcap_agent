import os
from dataclasses import dataclass
from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()


@dataclass(frozen=True)
class AppSettings:
    db_url: str
    max_rows: int
    sql_timeout_seconds: int
    debug: bool
    llm_model: str
    llm_base_url: str
    llm_timeout_seconds: int


def load_settings() -> AppSettings:
    db_url = os.getenv("FALCON_DB_URL")

    if not db_url:
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME")
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")

        required_env = {
            "DB_HOST": db_host,
            "DB_NAME": db_name,
            "DB_USER": db_user,
            "DB_PASSWORD": db_password,
        }
        missing_env = [name for name, value in required_env.items() if not value]
        if missing_env:
            raise ValueError(
                "Missing database configuration. Set FALCON_DB_URL or: "
                + ", ".join(missing_env)
            )

        db_url = URL.create(
            drivername="postgresql+psycopg2",
            username=db_user,
            password=db_password,
            host=db_host,
            port=int(db_port),
            database=db_name,
        ).render_as_string(hide_password=False)

    return AppSettings(
        db_url=db_url,
        max_rows=int(os.getenv("MAX_ROWS", "500")),
        sql_timeout_seconds=int(os.getenv("SQL_TIMEOUT_SECONDS", "60")),
        debug=os.getenv("DEBUG", "true").lower() == "true",
        llm_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        llm_base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        llm_timeout_seconds=int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30")),
    )