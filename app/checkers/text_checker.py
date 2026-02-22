# checker_text.py
from __future__ import annotations

from typing import Any


Verdict = tuple[str, str]
TaskDict = dict[str, Any]
CheckerDict = dict[str, Any]


def _normalize_text(value: Any) -> str:
    return str(value).strip().lower()


def _get_checker_dict(task: TaskDict) -> CheckerDict | None:
    checker = task.get("checker")
    if isinstance(checker, dict):
        return checker
    return None


def _get_mode(checker: CheckerDict) -> str:
    return _normalize_text(checker.get("mode", ""))


def _validate_answer_not_empty(answer: str) -> Verdict | None:
    if answer.strip():
        return None
    return "FAIL", "Ответ пустой. Напишите ответ и отправьте снова."


def _get_exact_expected_value(checker: CheckerDict) -> str | None:
    expected = checker.get("expected")
    if expected is None:
        return None
    return _normalize_text(expected)


def _check_exact_answer(checker: CheckerDict, answer: str) -> Verdict:
    expected_value = _get_exact_expected_value(checker)
    if expected_value is None:
        return "ERROR", "Проверка задачи настроена некорректно. Попробуйте позже."

    normalized_answer = _normalize_text(answer)
    if normalized_answer == expected_value:
        return "PASS", "Верно."

    return "FAIL", "Ответ не совпадает. Попробуйте еще раз."


def _normalize_keywords(raw_keywords: list[Any]) -> list[str]:
    normalized: list[str] = []
    for item in raw_keywords:
        keyword = _normalize_text(item)
        if keyword:
            normalized.append(keyword)
    return normalized


def _get_keywords_list(checker: CheckerDict) -> list[str] | None:
    raw_keywords = checker.get("keywords")
    if not isinstance(raw_keywords, list) or not raw_keywords:
        return None

    keywords = _normalize_keywords(raw_keywords)
    if not keywords:
        return None

    return keywords


def _find_matched_keywords(answer: str, keywords: list[str]) -> list[str]:
    normalized_answer = _normalize_text(answer)

    matched: list[str] = []
    for keyword in keywords:
        if keyword in normalized_answer:
            matched.append(keyword)

    return matched


def _build_keywords_result(matched_keywords: list[str], total_keywords: int) -> Verdict:
    matched_count = len(matched_keywords)

    if matched_count == total_keywords:
        return "PASS", "Отлично, ответ полный и верный."

    if matched_count > 0:
        return (
            "PARTIAL",
            (
                f"Ответ частично верный: найдено {matched_count} из {total_keywords} ключевых слов. "
                f"Есть правильные идеи: {', '.join(matched_keywords)}. "
                "Попробуйте дополнить ответ."
            ),
        )

    return "FAIL", "Пока не вижу ключевых идей в ответе. Попробуйте переформулировать."


def _check_keywords_answer(checker: CheckerDict, answer: str) -> Verdict:
    keywords = _get_keywords_list(checker)
    if keywords is None:
        return "ERROR", "Проверка задачи настроена некорректно. Попробуйте позже."

    matched_keywords = _find_matched_keywords(answer, keywords)
    return _build_keywords_result(matched_keywords, len(keywords))


def _check_answer_by_mode(checker: CheckerDict, answer: str) -> Verdict:
    mode = _get_mode(checker)

    if mode == "exact":
        return _check_exact_answer(checker, answer)

    if mode == "keywords":
        return _check_keywords_answer(checker, answer)

    return "ERROR", "Проверка задачи пока не настроена. Попробуйте позже."


def check_text_answer(task: dict, answer: str) -> tuple[str, str]:
    empty_answer_result = _validate_answer_not_empty(answer)
    if empty_answer_result is not None:
        return empty_answer_result

    checker = _get_checker_dict(task)
    if checker is None:
        return "ERROR", "Проверка задачи пока не настроена. Попробуйте позже."

    return _check_answer_by_mode(checker, answer)