# CS50 Edu Bot (MVP)

MVP Telegram-бот для обучения программированию: лекции, задачи, прогресс и базовая проверка ответов.

## Стек
- Python 3.11+
- aiogram 3.x
- SQLite (sqlite3)
- JSON (lessons/tasks content)
- python-dotenv

## Возможности MVP
- Просмотр лекций
- Просмотр задач по урокам
- Отправка ответа на задачу
- Базовая проверка (text/quiz/debug)
- Отображение прогресса пользователя

## Структура проекта
```text
.
├─ app/                  # (если у тебя есть app-модуль)
├─ handlers/             # navigation / solve handlers
├─ checkers/             # checker_text.py / checker_code.py
├─ content/              # lessons.json / tasks.json
├─ runtime/              # bot.db, временные файлы
├─ .env.example
├─ requirements.txt
└─ README.md