# content.py
from __future__ import annotations

from pathlib import Path
import json
from typing import Any


class ContentStore:
    """
    Простое хранилище контента для lessons.json и tasks.json.

    Ожидаемый минимум:
    - lessons.json -> список словарей, у каждого есть "id"
    - tasks.json   -> список словарей, у каждого есть "id" и "lesson_id"
    """

    def __init__(self, lessons_path: str, tasks_path: str) -> None:
        self.lessons_path: Path = Path(lessons_path)
        self.tasks_path: Path = Path(tasks_path)

        self._lessons: list[dict[str, Any]] = []
        self._tasks: list[dict[str, Any]] = []

        self.lessons_by_id: dict[str, dict[str, Any]] = {}
        self.tasks_by_id: dict[str, dict[str, Any]] = {}
        self.tasks_by_lesson: dict[str, list[dict[str, Any]]] = {}

    def load(self) -> None:
        """Загружает lessons/tasks из JSON и строит индексы."""
        lessons_raw = self._read_json_file(self.lessons_path)
        tasks_raw = self._read_json_file(self.tasks_path)

        if not isinstance(lessons_raw, list):
            raise ValueError(
                f"Некорректная структура в {self.lessons_path.name}: "
                "ожидается JSON-массив (list)"
            )
        if not isinstance(tasks_raw, list):
            raise ValueError(
                f"Некорректная структура в {self.tasks_path.name}: "
                "ожидается JSON-массив (list)"
            )

        self._validate_lessons(lessons_raw)
        self._validate_tasks(tasks_raw)

        # сохраняем "как есть" (копия списка)
        self._lessons = list(lessons_raw)
        self._tasks = list(tasks_raw)

        # строим индексы
        self.lessons_by_id = {str(lesson["id"]): lesson for lesson in self._lessons}
        self.tasks_by_id = {str(task["id"]): task for task in self._tasks}

        self.tasks_by_lesson = {}
        for task in self._tasks:
            lesson_id = str(task["lesson_id"])
            self.tasks_by_lesson.setdefault(lesson_id, []).append(task)

    def get_lessons(self) -> list[dict]:
        """Возвращает список уроков."""
        return self._lessons

    def get_lesson(self, lesson_id: str) -> dict | None:
        """Возвращает урок по id или None."""
        return self.lessons_by_id.get(lesson_id)

    def get_tasks_by_lesson(self, lesson_id: str) -> list[dict]:
        """Возвращает список задач урока (или пустой список)."""
        return self.tasks_by_lesson.get(lesson_id, [])

    def get_task(self, task_id: str) -> dict | None:
        """Возвращает задачу по id или None."""
        return self.tasks_by_id.get(task_id)

    # --------------------
    # Internal helpers
    # --------------------

    def _read_json_file(self, path: Path) -> Any:
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Путь не является файлом: {path}")

        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Невалидный JSON в файле {path.name}: "
                f"строка {e.lineno}, колонка {e.colno} ({e.msg})"
            ) from e

    def _validate_lessons(self, lessons: list[Any]) -> None:
        seen_ids: set[str] = set()

        for i, lesson in enumerate(lessons):
            if not isinstance(lesson, dict):
                raise ValueError(
                    f"Некорректный элемент в {self.lessons_path.name}[{i}]: "
                    "ожидается объект (dict)"
                )

            if "id" not in lesson:
                raise KeyError(
                    f"Отсутствует ключ 'id' в {self.lessons_path.name}[{i}]"
                )

            lesson_id = str(lesson["id"])
            if not lesson_id.strip():
                raise ValueError(
                    f"Пустой lesson id в {self.lessons_path.name}[{i}]"
                )

            if lesson_id in seen_ids:
                raise ValueError(f"Дубликат lesson id: '{lesson_id}'")
            seen_ids.add(lesson_id)

    def _validate_tasks(self, tasks: list[Any]) -> None:
        seen_ids: set[str] = set()

        for i, task in enumerate(tasks):
            if not isinstance(task, dict):
                raise ValueError(
                    f"Некорректный элемент в {self.tasks_path.name}[{i}]: "
                    "ожидается объект (dict)"
                )

            missing_keys = [key for key in ("id", "lesson_id") if key not in task]
            if missing_keys:
                raise KeyError(
                    f"Отсутствуют ключи {missing_keys} в {self.tasks_path.name}[{i}]"
                )

            task_id = str(task["id"])
            lesson_id = str(task["lesson_id"])

            if not task_id.strip():
                raise ValueError(f"Пустой task id в {self.tasks_path.name}[{i}]")
            if not lesson_id.strip():
                raise ValueError(
                    f"Пустой lesson_id в {self.tasks_path.name}[{i}]"
                )

            if task_id in seen_ids:
                raise ValueError(f"Дубликат task id: '{task_id}'")
            seen_ids.add(task_id)