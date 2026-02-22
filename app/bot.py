# bot.py
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher

import config as config_module
from content import ContentStore
from db import Database
import handlers_navigation
import handlers_solve


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def get_attr(obj: Any, *names: str) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def load_settings() -> Any:
    if hasattr(config_module, "load_settings") and callable(config_module.load_settings):
        return config_module.load_settings()

    if hasattr(config_module, "get_settings") and callable(config_module.get_settings):
        return config_module.get_settings()

    settings_class = getattr(config_module, "Settings", None)
    if settings_class is None:
        raise RuntimeError(
            "Не удалось загрузить настройки. "
            "Ожидается config.py с load_settings()/get_settings() или классом Settings."
        )

    from_env = getattr(settings_class, "from_env", None)
    if callable(from_env):
        return from_env()

    return settings_class()


def require_string_setting(settings: Any, field_name: str, *aliases: str) -> str:
    value = get_attr(settings, field_name, *aliases)
    if not value or not str(value).strip():
        raise RuntimeError(f"Не задано значение '{field_name}' в настройках.")
    return str(value).strip()


def get_bot_token(settings: Any) -> str:
    return require_string_setting(settings, "bot_token", "BOT_TOKEN", "token")


def ensure_runtime_dir(settings: Any, logger: logging.Logger) -> None:
    runtime_dir_value = get_attr(settings, "runtime_dir", "RUNTIME_DIR")
    if not runtime_dir_value:
        return

    runtime_dir = Path(str(runtime_dir_value))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Runtime dir ready: %s", runtime_dir)


def create_database(settings: Any, logger: logging.Logger) -> Database:
    db_path = require_string_setting(settings, "db_path", "DB_PATH")
    database = Database(db_path)
    database.init()
    logger.info("Database initialized: %s", db_path)
    return database


def load_content_store(settings: Any, logger: logging.Logger) -> ContentStore:
    lessons_path = require_string_setting(settings, "lessons_path", "LESSONS_PATH")
    tasks_path = require_string_setting(settings, "tasks_path", "TASKS_PATH")

    content_store = ContentStore(lessons_path=lessons_path, tasks_path=tasks_path)
    try:
        content_store.load()
    except Exception as error:
        raise RuntimeError(
            f"Не удалось загрузить контент (lessons/tasks): {error}"
        ) from error

    logger.info("Content loaded: lessons=%s, tasks=%s", lessons_path, tasks_path)
    return content_store


def create_bot_and_dispatcher(settings: Any) -> tuple[Bot, Dispatcher]:
    token = get_bot_token(settings)
    bot = Bot(token=token)
    dispatcher = Dispatcher()
    return bot, dispatcher


def register_navigation_dependencies(
    db: Database,
    content: ContentStore,
    settings: Any,
) -> None:
    if not hasattr(handlers_navigation, "register_dependencies"):
        raise RuntimeError(
            "В handlers_navigation.py отсутствует register_dependencies(...)."
        )

    handlers_navigation.register_dependencies(db=db, content=content, settings=settings)


def register_solve_dependencies(
    db: Database,
    content: ContentStore,
    settings: Any,
) -> None:
    if not hasattr(handlers_solve, "register_dependencies"):
        raise RuntimeError("В handlers_solve.py отсутствует register_dependencies(...).")

    checker_text = get_attr(settings, "checker_text")
    checker_code = get_attr(settings, "checker_code")

    handlers_solve.register_dependencies(
        db=db,
        content=content,
        settings=settings,
        checker_text=checker_text,
        checker_code=checker_code,
    )


def include_routers(dispatcher: Dispatcher) -> None:
    if not hasattr(handlers_navigation, "router"):
        raise RuntimeError("В handlers_navigation.py отсутствует router.")
    if not hasattr(handlers_solve, "router"):
        raise RuntimeError("В handlers_solve.py отсутствует router.")

    dispatcher.include_router(handlers_navigation.router)
    dispatcher.include_router(handlers_solve.router)


async def run_polling(bot: Bot, dispatcher: Dispatcher, logger: logging.Logger) -> None:
    logger.info("Starting bot polling...")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot stopped.")


async def _main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    settings = load_settings()
    ensure_runtime_dir(settings, logger)

    database = create_database(settings, logger)
    content_store = load_content_store(settings, logger)

    bot, dispatcher = create_bot_and_dispatcher(settings)

    register_navigation_dependencies(database, content_store, settings)
    register_solve_dependencies(database, content_store, settings)
    include_routers(dispatcher)

    await run_polling(bot, dispatcher, logger)


def main() -> None:
    asyncio.run(_main())