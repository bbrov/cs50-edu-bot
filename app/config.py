# config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    bot_token: str
    db_path: str
    lessons_path: str
    tasks_path: str
    runtime_dir: str
    code_timeout_sec: int


def _get_project_root() -> Path:
    return Path(__file__).resolve().parent


def _load_env_file() -> None:
    load_dotenv()


def _read_env_string(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        return ""
    return value.strip()


def _read_env_int(name: str, default: int) -> int:
    raw_value = _read_env_string(name, str(default))
    try:
        return int(raw_value)
    except ValueError as error:
        raise RuntimeError(
            f"Переменная окружения {name} должна быть целым числом. "
            f"Сейчас: {raw_value!r}"
        ) from error


def _require_bot_token() -> str:
    token = _read_env_string("BOT_TOKEN")
    if token:
        return token

    raise RuntimeError(
        "BOT_TOKEN пустой или не задан. "
        "Добавьте BOT_TOKEN в .env файл."
    )


def _build_default_paths(project_root: Path) -> tuple[str, str, str, str]:
    default_db_path = str(project_root / "runtime" / "bot.db")
    default_lessons_path = str(project_root / "content" / "lessons.json")
    default_tasks_path = str(project_root / "content" / "tasks.json")
    default_runtime_dir = str(project_root / "runtime")
    return (
        default_db_path,
        default_lessons_path,
        default_tasks_path,
        default_runtime_dir,
    )


def get_settings() -> Settings:
    _load_env_file()

    project_root = _get_project_root()
    (
        default_db_path,
        default_lessons_path,
        default_tasks_path,
        default_runtime_dir,
    ) = _build_default_paths(project_root)

    bot_token = _require_bot_token()
    db_path = _read_env_string("DB_PATH", default_db_path)
    lessons_path = _read_env_string("CONTENT_LESSONS", default_lessons_path)
    tasks_path = _read_env_string("CONTENT_TASKS", default_tasks_path)
    runtime_dir = _read_env_string("RUNTIME_DIR", default_runtime_dir)
    code_timeout_sec = _read_env_int("CODE_TIMEOUT_SEC", 5)

    return Settings(
        bot_token=bot_token,
        db_path=db_path,
        lessons_path=lessons_path,
        tasks_path=tasks_path,
        runtime_dir=runtime_dir,
        code_timeout_sec=code_timeout_sec,
    )