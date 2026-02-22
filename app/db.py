# db.py
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    def conn(self) -> sqlite3.Connection:
        db_path = Path(self.path)
        if db_path.parent and not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(str(db_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def init(self) -> None:
        with self.conn() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lessons_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    lesson_id TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    last_opened_at TEXT NOT NULL,
                    UNIQUE(user_id, lesson_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tasks_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, task_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    answer_text TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS hints_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id TEXT NOT NULL,
                    hint_key TEXT,
                    used_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_users_tg_id ON users(tg_id);
                CREATE INDEX IF NOT EXISTS idx_lessons_user_id ON lessons_progress(user_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks_progress(user_id);
                CREATE INDEX IF NOT EXISTS idx_submissions_user_task ON submissions(user_id, task_id);
                """
            )

    def upsert_user(self, tg_id: int, username: str | None) -> None:
        if tg_id <= 0:
            raise ValueError("tg_id must be a positive integer")

        now = self._now()

        with self.conn() as con:
            con.execute(
                """
                INSERT INTO users (tg_id, username, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET
                    username = excluded.username,
                    updated_at = excluded.updated_at
                """,
                (tg_id, username, now, now),
            )

    def open_lesson(self, tg_id: int, lesson_id: str) -> None:
        lesson_id = (lesson_id or "").strip()
        if not lesson_id:
            raise ValueError("lesson_id cannot be empty")

        with self.conn() as con:
            user_id = self._get_or_create_user_id(con, tg_id)
            now = self._now()

            con.execute(
                """
                INSERT INTO lessons_progress (user_id, lesson_id, opened_at, last_opened_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, lesson_id) DO UPDATE SET
                    last_opened_at = excluded.last_opened_at
                """,
                (user_id, lesson_id, now, now),
            )

    def set_task_status(self, tg_id: int, task_id: str, status: str) -> None:
        task_id = (task_id or "").strip()
        status = (status or "").strip().lower()

        if not task_id:
            raise ValueError("task_id cannot be empty")
        if status not in self._allowed_statuses():
            raise ValueError(f"status must be one of: {sorted(self._allowed_statuses())}")

        with self.conn() as con:
            user_id = self._get_or_create_user_id(con, tg_id)
            now = self._now()

            con.execute(
                """
                INSERT INTO tasks_progress (user_id, task_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, task_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (user_id, task_id, status, now),
            )

    def get_task_status(self, tg_id: int, task_id: str) -> str:
        task_id = (task_id or "").strip()
        if not task_id:
            return "not_started"

        with self.conn() as con:
            user_id = self._get_user_id(con, tg_id)
            if user_id is None:
                return "not_started"

            row = con.execute(
                """
                SELECT status
                FROM tasks_progress
                WHERE user_id = ? AND task_id = ?
                """,
                (user_id, task_id),
            ).fetchone()

            if row is None:
                return "not_started"

            status = row["status"]
            return status if isinstance(status, str) and status else "not_started"

    def add_submission(
        self,
        tg_id: int,
        task_id: str,
        answer_text: str,
        verdict: str,
        feedback: str,
    ) -> None:
        task_id = (task_id or "").strip()
        answer_text = answer_text if answer_text is not None else ""
        verdict = (verdict or "").strip().lower()
        feedback = feedback if feedback is not None else ""

        if not task_id:
            raise ValueError("task_id cannot be empty")
        if verdict not in self._allowed_verdicts():
            raise ValueError(f"verdict must be one of: {sorted(self._allowed_verdicts())}")

        with self.conn() as con:
            user_id = self._get_or_create_user_id(con, tg_id)
            attempt_no = self._get_attempt_no_by_user_id(con, user_id, task_id) + 1
            now = self._now()

            con.execute(
                """
                INSERT INTO submissions (
                    user_id, task_id, attempt_no, answer_text, verdict, feedback, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, task_id, attempt_no, answer_text, verdict, feedback, now),
            )

            # Автообновление статуса задачи по вердикту (можно убрать, если хочешь делать это только вручную)
            auto_status = "done" if verdict == "correct" else "in_progress"
            con.execute(
                """
                INSERT INTO tasks_progress (user_id, task_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, task_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (user_id, task_id, auto_status, now),
            )

    def get_attempt_no(self, tg_id: int, task_id: str) -> int:
        task_id = (task_id or "").strip()
        if not task_id:
            return 0

        with self.conn() as con:
            user_id = self._get_user_id(con, tg_id)
            if user_id is None:
                return 0
            return self._get_attempt_no_by_user_id(con, user_id, task_id)

    def get_progress_summary(
        self,
        tg_id: int,
        lesson_ids: list[str],
        lesson_task_map: dict[str, list[str]],
    ) -> dict[str, Any]:
        clean_lesson_ids = [lid.strip() for lid in lesson_ids if isinstance(lid, str) and lid.strip()]

        with self.conn() as con:
            user_id = self._get_user_id(con, tg_id)
            if user_id is None:
                return self._empty_summary(clean_lesson_ids, lesson_task_map)

            # Открытые уроки
            opened_rows = con.execute(
                """
                SELECT lesson_id
                FROM lessons_progress
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchall()
            opened_lessons = {str(row["lesson_id"]) for row in opened_rows}

            # Статусы задач
            task_rows = con.execute(
                """
                SELECT task_id, status
                FROM tasks_progress
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchall()
            task_status_map: dict[str, str] = {}
            for row in task_rows:
                task_id = str(row["task_id"])
                status = str(row["status"]) if row["status"] else "not_started"
                task_status_map[task_id] = status

            # Кол-во попыток по задачам
            attempts_rows = con.execute(
                """
                SELECT task_id, COUNT(*) AS cnt
                FROM submissions
                WHERE user_id = ?
                GROUP BY task_id
                """,
                (user_id,),
            ).fetchall()
            attempts_map = {str(row["task_id"]): int(row["cnt"]) for row in attempts_rows}

            lessons_data: list[dict[str, Any]] = []
            total_tasks = 0
            total_done = 0

            for lesson_id in clean_lesson_ids:
                lesson_tasks_raw = lesson_task_map.get(lesson_id, [])
                lesson_tasks = [t.strip() for t in lesson_tasks_raw if isinstance(t, str) and t.strip()]

                tasks_data: list[dict[str, Any]] = []
                done_count = 0

                for task_id in lesson_tasks:
                    status = task_status_map.get(task_id, "not_started")
                    attempts = attempts_map.get(task_id, 0)

                    if status == "done":
                        done_count += 1

                    tasks_data.append(
                        {
                            "task_id": task_id,
                            "status": status,
                            "attempts": attempts,
                        }
                    )

                total_tasks += len(lesson_tasks)
                total_done += done_count

                lessons_data.append(
                    {
                        "lesson_id": lesson_id,
                        "opened": lesson_id in opened_lessons,
                        "tasks_total": len(lesson_tasks),
                        "tasks_done": done_count,
                        "tasks": tasks_data,
                    }
                )

            percent = int((total_done / total_tasks) * 100) if total_tasks > 0 else 0

            return {
                "tg_id": tg_id,
                "lessons_total": len(clean_lesson_ids),
                "lessons_opened": sum(1 for lid in clean_lesson_ids if lid in opened_lessons),
                "tasks_total": total_tasks,
                "tasks_done": total_done,
                "progress_percent": percent,
                "lessons": lessons_data,
            }

    # ---------------------------
    # Internal helpers
    # ---------------------------

    def _get_user_id(self, con: sqlite3.Connection, tg_id: int) -> int | None:
        if tg_id <= 0:
            return None

        row = con.execute(
            """
            SELECT id
            FROM users
            WHERE tg_id = ?
            """,
            (tg_id,),
        ).fetchone()
        if row is None:
            return None
        return int(row["id"])

    def _get_or_create_user_id(self, con: sqlite3.Connection, tg_id: int) -> int:
        if tg_id <= 0:
            raise ValueError("tg_id must be a positive integer")

        user_id = self._get_user_id(con, tg_id)
        if user_id is not None:
            return user_id

        now = self._now()
        con.execute(
            """
            INSERT INTO users (tg_id, username, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (tg_id, None, now, now),
        )
        row = con.execute(
            """
            SELECT id
            FROM users
            WHERE tg_id = ?
            """,
            (tg_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to create user")
        return int(row["id"])

    def _get_attempt_no_by_user_id(self, con: sqlite3.Connection, user_id: int, task_id: str) -> int:
        row = con.execute(
            """
            SELECT COALESCE(MAX(attempt_no), 0) AS max_attempt
            FROM submissions
            WHERE user_id = ? AND task_id = ?
            """,
            (user_id, task_id),
        ).fetchone()

        if row is None:
            return 0
        return int(row["max_attempt"] or 0)

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    @staticmethod
    def _allowed_statuses() -> set[str]:
        return {"not_started", "in_progress", "done"}

    @staticmethod
    def _allowed_verdicts() -> set[str]:
        return {"correct", "wrong", "error"}

    def _empty_summary(
        self,
        lesson_ids: list[str],
        lesson_task_map: dict[str, list[str]],
    ) -> dict[str, Any]:
        lessons_data: list[dict[str, Any]] = []
        total_tasks = 0

        for lesson_id in lesson_ids:
            lesson_tasks_raw = lesson_task_map.get(lesson_id, [])
            lesson_tasks = [t.strip() for t in lesson_tasks_raw if isinstance(t, str) and t.strip()]
            total_tasks += len(lesson_tasks)

            lessons_data.append(
                {
                    "lesson_id": lesson_id,
                    "opened": False,
                    "tasks_total": len(lesson_tasks),
                    "tasks_done": 0,
                    "tasks": [
                        {
                            "task_id": task_id,
                            "status": "not_started",
                            "attempts": 0,
                        }
                        for task_id in lesson_tasks
                    ],
                }
            )

        return {
            "tg_id": None,
            "lessons_total": len(lesson_ids),
            "lessons_opened": 0,
            "tasks_total": total_tasks,
            "tasks_done": 0,
            "progress_percent": 0,
            "lessons": lessons_data,
        }
