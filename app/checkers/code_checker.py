# checker_code.py
# WARNING: MVP-only checker. This runs user Python code on the host machine (no sandbox / no Docker).
# Use only for simple trusted tasks in early development.

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


Verdict = tuple[str, str]
TaskDict = dict[str, Any]
TestCase = dict[str, Any]


def _get_task_id(task: TaskDict) -> str:
    task_id = str(task.get("id", "")).strip()
    return task_id or "unknown_task"


def _get_checker(task: TaskDict) -> dict[str, Any] | None:
    checker = task.get("checker")
    if isinstance(checker, dict):
        return checker
    return None


def _get_tests_from_checker(checker: dict[str, Any]) -> list[TestCase] | None:
    tests = checker.get("tests")
    if isinstance(tests, list) and tests:
        return tests
    return None


def _get_task_tests(task: TaskDict) -> list[TestCase] | None:
    checker = _get_checker(task)
    if checker is None:
        return None
    return _get_tests_from_checker(checker)


def _check_code_not_empty(code: str) -> Verdict | None:
    if code.strip():
        return None
    return "ERROR", "Код пустой. Отправьте Python-код для проверки."


def _format_syntax_error(error: SyntaxError) -> str:
    line_number = error.lineno or "?"
    error_line = (error.text or "").strip()

    message = f"SyntaxError: строка {line_number}"
    if error_line:
        message += f" -> {error_line}"
    if error.msg:
        message += f" ({error.msg})"

    return message


def _check_python_syntax(code: str) -> Verdict | None:
    try:
        ast.parse(code)
    except SyntaxError as error:
        return "ERROR", _format_syntax_error(error)

    return None


def _create_task_runtime_dir(runtime_dir: str, task_id: str) -> Path:
    task_dir = Path(runtime_dir) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def _save_code_to_temp_file(task_dir: Path, code: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".py",
        prefix="submission_",
        dir=task_dir,
        delete=False,
    ) as temp_file:
        temp_file.write(code)
        return Path(temp_file.name)


def _normalize_output(value: Any) -> str:
    return str(value).strip()


def _run_python_script(
    script_path: Path,
    stdin_text: str,
    timeout_sec: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script_path)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        encoding="utf-8",
    )


def _extract_test_input(test: TestCase) -> str:
    return str(test.get("input", ""))


def _extract_expected_output(test: TestCase) -> str:
    return _normalize_output(test.get("expected_output", ""))


def _format_runtime_error(test_number: int, stderr_text: str) -> Verdict:
    error_text = _normalize_output(stderr_text)
    if not error_text:
        error_text = "Runtime Error без текста ошибки."
    return "ERROR", f"Тест {test_number}: Runtime Error\n{error_text}"


def _format_fail_message(
    test_number: int,
    expected_output: str,
    actual_output: str,
) -> Verdict:
    return (
        "FAIL",
        (
            f"Тест {test_number} не пройден.\n"
            f"Ожидалось: {expected_output!r}\n"
            f"Получено: {actual_output!r}"
        ),
    )


def _run_test_case(
    script_path: Path,
    test: TestCase,
    timeout_sec: int,
    test_number: int,
) -> Verdict | None:
    test_input = _extract_test_input(test)
    expected_output = _extract_expected_output(test)

    try:
        result = _run_python_script(
            script_path=script_path,
            stdin_text=test_input,
            timeout_sec=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", f"Тест {test_number}: превышен лимит времени ({timeout_sec} сек)."
    except Exception as error:
        return "ERROR", f"Тест {test_number}: ошибка запуска кода: {error}"

    if result.returncode != 0:
        return _format_runtime_error(test_number, result.stderr)

    actual_output = _normalize_output(result.stdout)
    if actual_output != expected_output:
        return _format_fail_message(test_number, expected_output, actual_output)

    return None


def _validate_test_object(test: Any, test_number: int) -> Verdict | None:
    if isinstance(test, dict):
        return None
    return "ERROR", f"Проверка не настроена: тест {test_number} имеет неверный формат."


def _run_all_tests(
    script_path: Path,
    tests: list[TestCase],
    timeout_sec: int,
) -> Verdict:
    for test_number, test in enumerate(tests, start=1):
        invalid_test_error = _validate_test_object(test, test_number)
        if invalid_test_error is not None:
            return invalid_test_error

        test_result = _run_test_case(
            script_path=script_path,
            test=test,
            timeout_sec=timeout_sec,
            test_number=test_number,
        )
        if test_result is not None:
            return test_result

    return "PASS", f"Все тесты пройдены: {len(tests)} из {len(tests)}."


def check_python_code(
    task: dict,
    code: str,
    runtime_dir: str,
    timeout_sec: int,
) -> tuple[str, str]:
    empty_code_error = _check_code_not_empty(code)
    if empty_code_error is not None:
        return empty_code_error

    syntax_error = _check_python_syntax(code)
    if syntax_error is not None:
        return syntax_error

    tests = _get_task_tests(task)
    if tests is None:
        return (
            "ERROR",
            "Проверка не настроена: в task['checker']['tests'] нет корректных тестов.",
        )

    task_id = _get_task_id(task)
    task_dir = _create_task_runtime_dir(runtime_dir, task_id)
    script_path = _save_code_to_temp_file(task_dir, code)

    return _run_all_tests(
        script_path=script_path,
        tests=tests,
        timeout_sec=timeout_sec,
    )