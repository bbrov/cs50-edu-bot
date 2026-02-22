# keyboards.py
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


STATUS_EMOJI: dict[str, str] = {
    "not_started": "⚪",
    "in_progress": "🟡",
    "solved": "🟢",
}


def main_menu_kb() -> ReplyKeyboardMarkup:
    """
    Главное reply-меню MVP.
    Без callback_data, только текстовые кнопки.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Лекции"), KeyboardButton(text="🧩 Задачи")],
            [KeyboardButton(text="📈 Прогресс"), KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите раздел",
    )


def lessons_kb(lessons: list[dict]) -> InlineKeyboardMarkup:
    """
    Список лекций (inline).
    Ожидается, что у каждой лекции есть:
    - id (str/int)
    - title (str) или name (str)
    """
    rows: list[list[InlineKeyboardButton]] = []

    for lesson in lessons:
        lesson_id = str(lesson.get("id", ""))
        title = str(lesson.get("title") or lesson.get("name") or f"Лекция {lesson_id}").strip()

        if not lesson_id:
            continue

        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"lesson:{lesson_id}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def tasks_kb(tasks: list[dict], statuses: dict[str, str]) -> InlineKeyboardMarkup:
    """
    Список задач (inline) со статусами.
    statuses: {task_id: status}
    status in {"not_started", "in_progress", "solved"}
    """
    rows: list[list[InlineKeyboardButton]] = []

    for idx, task in enumerate(tasks, start=1):
        task_id = str(task.get("id", ""))
        if not task_id:
            continue

        title = str(task.get("title") or task.get("name") or f"Задача {idx}").strip()

        raw_status = statuses.get(task_id, "not_started")
        emoji = STATUS_EMOJI.get(raw_status, STATUS_EMOJI["not_started"])

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{emoji} {title}",
                    callback_data=f"task:{task_id}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def task_card_kb(task_id: str) -> InlineKeyboardMarkup:
    """
    Клавиатура карточки задачи:
    - Подсказки (3 уровня)
    - Отправить решение
    """
    safe_task_id = str(task_id)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💡 Подсказка 1",
                    callback_data=f"hint:{safe_task_id}:1",
                ),
                InlineKeyboardButton(
                    text="💡 Подсказка 2",
                    callback_data=f"hint:{safe_task_id}:2",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💡 Подсказка 3",
                    callback_data=f"hint:{safe_task_id}:3",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Отправить решение",
                    callback_data=f"submit:{safe_task_id}",
                ),
            ],
        ]
    )


def next_task_kb(current_task: dict, lesson_tasks: list[dict]) -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой "Следующая задача".
    Если текущая задача последняя или не найдена — возвращает пустую inline-клавиатуру.
    """
    current_id = str(current_task.get("id", ""))
    if not current_id:
        return InlineKeyboardMarkup(inline_keyboard=[])

    next_task_id: str | None = None

    for i, task in enumerate(lesson_tasks):
        task_id = str(task.get("id", ""))
        if task_id == current_id:
            if i + 1 < len(lesson_tasks):
                next_task_id = str(lesson_tasks[i + 1].get("id", ""))
                if not next_task_id:
                    next_task_id = None
            break

    if not next_task_id:
        return InlineKeyboardMarkup(inline_keyboard=[])

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➡️ Следующая задача",
                    callback_data=f"task:{next_task_id}",
                )
            ]
        ]
    )