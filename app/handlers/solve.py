# handlers_solve.py
from __future__ import annotations

from html import escape
from typing import Any, Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from states import SolveTaskState

router = Router()

# Зависимости регистрируются снаружи через register_dependencies(...)
_db = None
_content = None
_settings = None
_checker_text = None
_checker_code = None


def register_dependencies(db, content, settings, checker_text, checker_code) -> None:
    """
    Подключаем зависимости в модуль.
    Вызывать один раз при старте приложения.
    """
    global _db, _content, _settings, _checker_text, _checker_code
    _db = db
    _content = content
    _settings = settings
    _checker_text = checker_text
    _checker_code = checker_code


# =========================
# Внутренние helper-функции
# =========================

def _next_task_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Следующая задача", callback_data="next_task")]
        ]
    )


def _safe_answer_callback(callback: CallbackQuery, text: str, show_alert: bool = False) -> None:
    """
    Безопасный ответ на callback (если message уже неактуально/другие мелкие ошибки — не падаем).
    """
    try:
        if callback.answer:
            # aiogram async, но тут sync-обертка не нужна; используем напрямую в handlers.
            pass
    except Exception:
        pass


async def _try_call(obj: Any, method_names: list[str], *args, **kwargs) -> Any:
    """
    Пытается вызвать один из методов объекта.
    Удобно, если у тебя в db/content разные названия методов.
    """
    if obj is None:
        return None

    for name in method_names:
        fn = getattr(obj, name, None)
        if callable(fn):
            return await fn(*args, **kwargs)
    return None


async def _get_task(task_id: int) -> Optional[dict]:
    """
    Пытаемся получить задачу из content.
    Ожидаемый формат задачи (пример):
    {
        "id": 1,
        "title": "...",
        "expected_mode": "text" | "code",
        "question": "...",
        "hints": {"1": "...", "2": "..."}  # опционально
    }
    """
    task = await _try_call(_content, ["get_task", "get_task_by_id", "task_by_id"], task_id)
    if isinstance(task, dict):
        return task
    return None


async def _get_hint_text(task: dict, task_id: int, level: str) -> Optional[str]:
    """
    Получаем текст подсказки:
    1) через content.get_hint(...)
    2) через task['hints']
    """
    # Вариант 1: отдельный метод в content
    hint = await _try_call(_content, ["get_hint", "get_task_hint"], task_id, level)
    if isinstance(hint, str) and hint.strip():
        return hint.strip()
    if isinstance(hint, dict):
        # если content вернул dict {"text": "..."}
        txt = hint.get("text")
        if isinstance(txt, str) and txt.strip():
            return txt.strip()

    # Вариант 2: подсказки лежат внутри task
    hints = task.get("hints")
    if isinstance(hints, dict):
        # level может быть "1", "2", "basic" и т.д.
        for key in (level, str(level)):
            value = hints.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


async def _save_hint_open(user_id: int, task_id: int, level: str) -> None:
    """
    Сохраняем факт открытия подсказки. Не падаем, если метода нет.
    """
    # Поддержка нескольких возможных названий методов
    await _try_call(
        _db,
        ["mark_hint_opened", "save_hint_open", "log_hint_open", "open_hint"],
        user_id,
        task_id,
        level,
    )


async def _save_submission(
    user_id: int,
    task_id: int,
    answer_text: str,
    mode: str,
    verdict: str,
    feedback: str,
) -> None:
    """
    Сохраняем отправку решения. Не падаем, если конкретного метода нет.
    """
    # Вариант 1: единый метод save_submission(...)
    saved = await _try_call(
        _db,
        ["save_submission", "create_submission", "add_submission"],
        user_id=user_id,
        task_id=task_id,
        answer=answer_text,
        mode=mode,
        verdict=verdict,
        feedback=feedback,
    )
    if saved is not None:
        return

    # Вариант 2: позиционные параметры
    await _try_call(
        _db,
        ["save_submission", "create_submission", "add_submission"],
        user_id,
        task_id,
        answer_text,
        mode,
        verdict,
        feedback,
    )


async def _update_task_status(user_id: int, task_id: int, verdict: str) -> None:
    """
    Обновляем статус задачи у пользователя.
    Базовая логика:
    - PASS -> solved
    - PARTIAL -> in_progress
    - FAIL / ERROR / TIMEOUT -> attempted
    """
    if verdict == "PASS":
        status = "solved"
    elif verdict == "PARTIAL":
        status = "in_progress"
    else:
        status = "attempted"

    # Пытаемся сохранить status + verdict (если db умеет)
    updated = await _try_call(
        _db,
        ["update_task_status", "set_task_status", "upsert_task_status"],
        user_id=user_id,
        task_id=task_id,
        status=status,
        verdict=verdict,
    )
    if updated is not None:
        return

    # fallback на позиционные
    await _try_call(
        _db,
        ["update_task_status", "set_task_status", "upsert_task_status"],
        user_id,
        task_id,
        status,
        verdict,
    )


async def _run_checker(mode: str, task: dict, answer_text: str) -> tuple[str, str]:
    """
    Запуск checker и нормализация результата.
    Возвращает (verdict, feedback).
    Допустимые verdict:
      text -> PASS / PARTIAL / FAIL
      code -> PASS / FAIL / ERROR / TIMEOUT
    """
    if mode == "text":
        if _checker_text is None:
            return "FAIL", "Проверка текста временно недоступна."
        try:
            raw = await _call_checker(_checker_text, task=task, answer=answer_text, settings=_settings)
            verdict, feedback = _normalize_checker_result(raw, mode="text")
            return verdict, feedback
        except Exception as e:
            return "FAIL", f"Ошибка при проверке текстового ответа: {e}"

    if mode == "code":
        if _checker_code is None:
            return "ERROR", "Проверка кода временно недоступна."
        try:
            raw = await _call_checker(_checker_code, task=task, answer=answer_text, settings=_settings)
            verdict, feedback = _normalize_checker_result(raw, mode="code")
            return verdict, feedback
        except TimeoutError:
            return "TIMEOUT", "Превышено время выполнения решения."
        except Exception as e:
            return "ERROR", f"Ошибка при проверке кода: {e}"

    return "FAIL", "Неизвестный режим задачи."


async def _call_checker(checker: Any, task: dict, answer: str, settings: Any) -> Any:
    """
    Пытаемся вызвать checker в одном из популярных форматов.
    Это сделано, чтобы было проще подключить любой checker отдельно.
    """
    # 1) checker(task=..., answer=..., settings=...)
    try:
        return await checker(task=task, answer=answer, settings=settings)
    except TypeError:
        pass

    # 2) checker(task, answer, settings)
    try:
        return await checker(task, answer, settings)
    except TypeError:
        pass

    # 3) checker(task=..., answer=...)
    try:
        return await checker(task=task, answer=answer)
    except TypeError:
        pass

    # 4) checker(task, answer)
    return await checker(task, answer)


def _normalize_checker_result(raw: Any, mode: str) -> tuple[str, str]:
    """
    Нормализуем результат checker в (verdict, feedback).

    Поддерживаемые форматы checker:
    - {"verdict": "...", "feedback": "..."}
    - {"status": "...", "feedback": "..."}
    - ("PASS", "feedback")
    - "PASS"  (feedback будет пустой)
    """
    verdict = None
    feedback = ""

    if isinstance(raw, dict):
        verdict = raw.get("verdict") or raw.get("status")
        feedback = raw.get("feedback") or raw.get("message") or ""
    elif isinstance(raw, (tuple, list)) and len(raw) >= 1:
        verdict = raw[0]
        if len(raw) > 1:
            feedback = raw[1] or ""
    elif isinstance(raw, str):
        verdict = raw
        feedback = ""
    else:
        verdict = None
        feedback = "Некорректный ответ от checker."

    verdict = str(verdict or "").upper().strip()
    feedback = str(feedback or "").strip()

    allowed_text = {"PASS", "PARTIAL", "FAIL"}
    allowed_code = {"PASS", "FAIL", "ERROR", "TIMEOUT"}

    if mode == "text":
        if verdict not in allowed_text:
            return "FAIL", feedback or "Не удалось определить результат проверки текста."
        return verdict, feedback or _default_feedback(verdict)

    if mode == "code":
        if verdict not in allowed_code:
            return "ERROR", feedback or "Не удалось определить результат проверки кода."
        return verdict, feedback or _default_feedback(verdict)

    return "FAIL", "Неизвестный режим проверки."


def _default_feedback(verdict: str) -> str:
    defaults = {
        "PASS": "Решение принято.",
        "PARTIAL": "Частично верно. Попробуй улучшить ответ.",
        "FAIL": "Пока неверно. Попробуй ещё раз.",
        "ERROR": "Во время проверки произошла ошибка.",
        "TIMEOUT": "Превышено время выполнения.",
    }
    return defaults.get(verdict, "Проверка завершена.")


def _extract_answer_text(message: Message) -> str:
    """
    Безопасно достаём текст ответа.
    Поддержка text / caption. Пустые и служебные сообщения -> "".
    """
    if message.text and message.text.strip():
        return message.text.strip()
    if message.caption and message.caption.strip():
        return message.caption.strip()
    return ""


def _format_verdict_message(verdict: str, feedback: str) -> str:
    verdict_ru = {
        "PASS": "✅ PASS",
        "PARTIAL": "🟡 PARTIAL",
        "FAIL": "❌ FAIL",
        "ERROR": "⚠️ ERROR",
        "TIMEOUT": "⏱ TIMEOUT",
    }.get(verdict, verdict)

    safe_feedback = escape(feedback or "Без комментария.")
    return f"<b>Результат:</b> {verdict_ru}\n\n<b>Feedback:</b>\n{safe_feedback}"


# =========================
# Хендлеры
# =========================

@router.callback_query(F.data.startswith("submit:"))
async def submit_task_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """
    callback submit:<task_id>
    Переводим пользователя в состояние ожидания ответа.
    """
    try:
        _, task_id_raw = callback.data.split(":", 1)
        task_id = int(task_id_raw)
    except Exception:
        await callback.answer("Некорректный task_id.", show_alert=True)
        return

    task = await _get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    await state.set_state(SolveTaskState.waiting_for_answer)
    await state.update_data(task_id=task_id)

    await callback.answer("Отправьте ваш ответ сообщением.")
    if callback.message:
        await callback.message.answer(
            "Пришлите решение одним сообщением.\n"
            "После отправки я проверю и покажу результат."
        )


@router.callback_query(F.data.startswith("hint:"))
async def hint_callback(callback: CallbackQuery) -> None:
    """
    callback hint:<task_id>:<level>
    Показываем подсказку и сохраняем факт открытия в БД.
    """
    try:
        _, task_id_raw, level = callback.data.split(":", 2)
        task_id = int(task_id_raw)
    except Exception:
        await callback.answer("Некорректный формат подсказки.", show_alert=True)
        return

    task = await _get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    hint_text = await _get_hint_text(task, task_id, level)
    if not hint_text:
        await callback.answer("Подсказка не найдена.", show_alert=True)
        return

    # Сохраняем факт открытия подсказки (не блокируем UX, даже если БД упала)
    try:
        user_id = callback.from_user.id
        await _save_hint_open(user_id=user_id, task_id=task_id, level=level)
    except Exception:
        pass

    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"💡 <b>Подсказка ({escape(level)}):</b>\n{escape(hint_text)}"
        )


@router.message(SolveTaskState.waiting_for_answer)
async def handle_solution_submission(message: Message, state: FSMContext) -> None:
    """
    Получаем ответ пользователя, запускаем checker, сохраняем submission, обновляем статус.
    """
    # 1) Достаём task_id из state
    data = await state.get_data()
    task_id = data.get("task_id")

    if task_id is None:
        await message.answer(
            "Не удалось определить задачу для проверки.\n"
            "Открой задачу заново и нажми «Отправить решение»."
        )
        await state.clear()
        return

    # task_id мог быть сохранён строкой
    try:
        task_id = int(task_id)
    except Exception:
        await message.answer(
            "Некорректный идентификатор задачи.\n"
            "Открой задачу заново и попробуй ещё раз."
        )
        await state.clear()
        return

    # 2) Берём текст ответа (не падаем на пустых/неподдерживаемых сообщениях)
    answer_text = _extract_answer_text(message)
    if not answer_text:
        await message.answer(
            "Пустой ответ не подходит.\n"
            "Отправь текст решения одним сообщением."
        )
        return

    # 3) Получаем задачу и режим проверки
    task = await _get_task(task_id)
    if not task:
        await message.answer(
            "Задача не найдена или была удалена.\n"
            "Открой задачу заново."
        )
        await state.clear()
        return

    expected_mode = str(task.get("expected_mode", "")).lower().strip()
    if expected_mode not in {"text", "code"}:
        await message.answer(
            "У задачи не настроен режим проверки (text/code).\n"
            "Сообщи администратору."
        )
        await state.clear()
        return

    # 4) Вызываем checker
    verdict, feedback = await _run_checker(
        mode=expected_mode,
        task=task,
        answer_text=answer_text,
    )

    # 5) Сохраняем submission (ошибка БД не должна ломать ответ пользователю)
    user_id = message.from_user.id if message.from_user else 0
    try:
        await _save_submission(
            user_id=user_id,
            task_id=task_id,
            answer_text=answer_text,
            mode=expected_mode,
            verdict=verdict,
            feedback=feedback,
        )
    except Exception:
        # Можно залогировать, если у тебя есть logger
        pass

    # 6) Обновляем статус задачи
    try:
        await _update_task_status(user_id=user_id, task_id=task_id, verdict=verdict)
    except Exception:
        pass

    # 7) Отправляем вердикт + feedback + кнопку "Следующая задача"
    await message.answer(
        _format_verdict_message(verdict, feedback),
        reply_markup=_next_task_kb(),
    )

    # 8) Очищаем state (важно, чтобы следующий ответ не привязался к старой задаче)
    await state.clear()