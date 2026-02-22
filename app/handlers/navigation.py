# handlers_navigation.py
from __future__ import annotations

from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from keyboards import (
    lessons_kb,
    main_menu_kb,
    task_card_kb,
    tasks_kb,
)

router = Router()

_db: Any = None
_content: Any = None
_settings: Any = None


def register_dependencies(db: Any, content: Any, settings: Any = None) -> None:
    """Регистрирует зависимости (вызывается при старте приложения)."""
    global _db, _content, _settings
    _db = db
    _content = content
    _settings = settings


# ========= Helpers =========


def _ensure_dependencies() -> None:
    if _db is None or _content is None:
        raise RuntimeError(
            "handlers_navigation: зависимости не зарегистрированы. "
            "Вызови register_dependencies(db, content, settings)."
        )


def _safe_username(message: Message) -> str | None:
    user = message.from_user
    if not user:
        return None
    return user.username


def _status_to_human(status: str | None) -> str:
    mapping = {
        "not_started": "не начато",
        "in_progress": "решается",
        "solved": "решено",
    }
    return mapping.get(status or "not_started", "не начато")


def _get_task_status_for_user(tg_id: int, task_id: str) -> str:
    """
    Пытаемся получить статус через db.get_task_status(...).
    Поддерживаем несколько возможных форматов ответа:
    - строка ("not_started")
    - dict/Row с ключом status
    - None
    """
    try:
        raw = _db.get_task_status(tg_id, task_id)
    except Exception:
        return "not_started"

    if raw is None:
        return "not_started"

    if isinstance(raw, str):
        return raw

    if isinstance(raw, dict):
        return str(raw.get("status", "not_started"))

    # sqlite3.Row ведет себя почти как dict, но на всякий случай:
    try:
        return str(raw["status"])
    except Exception:
        return "not_started"


def _try_set_in_progress(tg_id: int, task_id: str, current_status: str) -> None:
    """Если задача впервые открыта — помечаем как in_progress (без падения хендлера)."""
    if current_status != "not_started":
        return
    try:
        _db.set_task_status(tg_id, task_id, "in_progress")
    except Exception:
        # Не валим навигацию, если этот метод еще не реализован/упал
        return


def _lessons_list_text(title: str = "Выберите лекцию:") -> str:
    lessons = _content.get_lessons() or []
    if not lessons:
        return "Список лекций пока пуст."
    return title


def _build_lesson_text(lesson: dict[str, Any]) -> str:
    topics = lesson.get("topics") or []
    topics_text = "\n".join(f"• {escape(str(t))}" for t in topics) if topics else "• Темы пока не добавлены"

    parts = [
        f"📚 <b>{escape(str(lesson.get('title', 'Без названия')))}</b>",
        "",
        escape(str(lesson.get("description", "Описание отсутствует."))),
        "",
        "<b>Темы:</b>",
        topics_text,
    ]

    video_url = lesson.get("video_url")
    if video_url:
        parts.extend(["", f"🎥 Видео: {escape(str(video_url))}"])

    parts.extend(["", "Ниже — список задач этой лекции."])
    return "\n".join(parts)


def _build_task_card_text(task: dict[str, Any], status: str) -> str:
    examples = task.get("examples") or []
    examples_text = "\n".join(f"• {escape(str(x))}" for x in examples) if examples else "• Нет примеров"

    lines = [
        f"🧩 <b>{escape(str(task.get('title', 'Без названия')))}</b>",
        f"Статус: <b>{escape(_status_to_human(status))}</b>",
        f"Сложность: {escape(str(task.get('difficulty', '—')))}",
        f"Тема: {escape(str(task.get('topic', '—')))}",
        f"Тип: {escape(str(task.get('type', '—')))}",
        "",
        "<b>Условие:</b>",
        escape(str(task.get("statement", "Условие отсутствует."))),
        "",
        "<b>Формат входных данных:</b>",
        escape(str(task.get("input_format", "—"))),
        "",
        "<b>Формат выходных данных:</b>",
        escape(str(task.get("output_format", "—"))),
        "",
        "<b>Примеры:</b>",
        examples_text,
    ]
    return "\n".join(lines)


def _build_progress_text(tg_id: int) -> str:
    lessons = _content.get_lessons() or []
    all_tasks: list[dict[str, Any]] = []

    for lesson in lessons:
        lesson_id = str(lesson.get("id", ""))
        if not lesson_id:
            continue
        lesson_tasks = _content.get_tasks_by_lesson(lesson_id) or []
        all_tasks.extend(lesson_tasks)

    total = len(all_tasks)
    solved = 0
    in_progress = 0
    not_started = 0

    for task in all_tasks:
        task_id = str(task.get("id", ""))
        if not task_id:
            continue
        status = _get_task_status_for_user(tg_id, task_id)
        if status == "solved":
            solved += 1
        elif status == "in_progress":
            in_progress += 1
        else:
            not_started += 1

    percent = int((solved / total) * 100) if total > 0 else 0

    lines = [
        "📈 <b>Ваш прогресс</b>",
        "",
        f"Всего задач: <b>{total}</b>",
        f"✅ Решено: <b>{solved}</b>",
        f"🟡 Решается: <b>{in_progress}</b>",
        f"⚪ Не начато: <b>{not_started}</b>",
        "",
        f"Прогресс по решённым: <b>{percent}%</b>",
    ]
    return "\n".join(lines)


def _lesson_statuses_for_user(tg_id: int, lesson_id: str) -> dict[str, str]:
    tasks = _content.get_tasks_by_lesson(lesson_id) or []
    statuses: dict[str, str] = {}
    for task in tasks:
        task_id = str(task.get("id", ""))
        if not task_id:
            continue
        statuses[task_id] = _get_task_status_for_user(tg_id, task_id)
    return statuses


# ========= Command handlers =========


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    _ensure_dependencies()

    if not message.from_user:
        await message.answer("Не удалось определить пользователя. Попробуйте снова.")
        return

    try:
        _db.upsert_user(message.from_user.id, _safe_username(message))
    except Exception:
        await message.answer("Ошибка регистрации пользователя. Попробуйте позже.")
        return

    text = (
        "Добро пожаловать в учебный бот.\n\n"
        "Что можно сделать:\n"
        "• открыть лекции\n"
        "• посмотреть задачи\n"
        "• проверить прогресс\n\n"
        "Используйте кнопки ниже или команды /menu, /help, /progress."
    )
    await message.answer(text, reply_markup=main_menu_kb())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    _ensure_dependencies()
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    _ensure_dependencies()
    text = (
        "Команды:\n"
        "/start — запуск бота\n"
        "/menu — показать меню\n"
        "/help — помощь\n"
        "/progress — ваш прогресс\n\n"
        "Навигация:\n"
        "• «📚 Лекции» — список лекций\n"
        "• «🧩 Задачи» — выбор лекции и задач\n"
        "• «📈 Прогресс» — статистика по задачам\n"
        "• «ℹ️ О боте» — кратко о проекте"
    )
    await message.answer(text, reply_markup=main_menu_kb())


@router.message(Command("progress"))
async def cmd_progress(message: Message) -> None:
    _ensure_dependencies()

    if not message.from_user:
        await message.answer("Не удалось определить пользователя.")
        return

    try:
        _db.upsert_user(message.from_user.id, _safe_username(message))
    except Exception:
        # Даже если upsert упал, попытаемся показать прогресс
        pass

    text = _build_progress_text(message.from_user.id)
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


# ========= Main menu button handlers =========


@router.message(F.text == "📚 Лекции")
async def btn_lessons(message: Message) -> None:
    _ensure_dependencies()
    lessons = _content.get_lessons() or []
    await message.answer(
        _lessons_list_text("📚 Выберите лекцию:"),
        reply_markup=lessons_kb(lessons),
    )


@router.message(F.text == "🧩 Задачи")
async def btn_tasks(message: Message) -> None:
    _ensure_dependencies()
    lessons = _content.get_lessons() or []
    await message.answer(
        _lessons_list_text("🧩 Сначала выберите лекцию, чтобы посмотреть задачи:"),
        reply_markup=lessons_kb(lessons),
    )


@router.message(F.text == "📈 Прогресс")
async def btn_progress(message: Message) -> None:
    _ensure_dependencies()

    if not message.from_user:
        await message.answer("Не удалось определить пользователя.")
        return

    text = _build_progress_text(message.from_user.id)
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.message(F.text == "ℹ️ О боте")
async def btn_about(message: Message) -> None:
    _ensure_dependencies()
    text = (
        "ℹ️ <b>О боте</b>\n\n"
        "MVP-бот для обучения программированию:\n"
        "• лекции в JSON\n"
        "• список задач по лекциям\n"
        "• отслеживание прогресса\n\n"
        "На текущем этапе бот показывает навигацию и карточки задач "
        "без проверки решений."
    )
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


# ========= Callback handlers =========


@router.callback_query(F.data.startswith("lesson:"))
async def cb_open_lesson(callback: CallbackQuery) -> None:
    _ensure_dependencies()

    if not callback.data:
        await callback.answer("Некорректный запрос.", show_alert=True)
        return

    if not callback.from_user:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    lesson_id = callback.data.split(":", 1)[1].strip()
    if not lesson_id:
        await callback.answer("Не передан ID лекции.", show_alert=True)
        return

    lesson = _content.get_lesson(lesson_id)
    if not lesson:
        await callback.answer("Лекция не найдена.", show_alert=True)
        return

    # Регистрируем пользователя и сохраняем факт открытия лекции
    try:
        _db.upsert_user(callback.from_user.id, callback.from_user.username)
    except Exception:
        pass

    try:
        _db.open_lesson(callback.from_user.id, lesson_id)
    except Exception:
        # Не ломаем UX, если логирование открытия временно не работает
        pass

    lesson_tasks = _content.get_tasks_by_lesson(lesson_id) or []
    statuses = _lesson_statuses_for_user(callback.from_user.id, lesson_id)

    text = _build_lesson_text(lesson)
    if not lesson_tasks:
        text += "\n\n⚠️ Для этой лекции пока нет задач."

    await callback.message.edit_text(
        text,
        reply_markup=tasks_kb(lesson_tasks, statuses) if lesson_tasks else None,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("task:"))
async def cb_open_task(callback: CallbackQuery) -> None:
    _ensure_dependencies()

    if not callback.data:
        await callback.answer("Некорректный запрос.", show_alert=True)
        return

    if not callback.from_user:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    task_id = callback.data.split(":", 1)[1].strip()
    if not task_id:
        await callback.answer("Не передан ID задачи.", show_alert=True)
        return

    task = _content.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    # Подстраховка: регистрируем пользователя
    try:
        _db.upsert_user(callback.from_user.id, callback.from_user.username)
    except Exception:
        pass

    current_status = _get_task_status_for_user(callback.from_user.id, task_id)

    # Если впервые открыли карточку — помечаем как "решается"
    _try_set_in_progress(callback.from_user.id, task_id, current_status)
    updated_status = _get_task_status_for_user(callback.from_user.id, task_id)

    text = _build_task_card_text(task, updated_status)

    await callback.message.edit_text(
        text,
        reply_markup=task_card_kb(task_id),
        parse_mode="HTML",
    )
    await callback.answer()