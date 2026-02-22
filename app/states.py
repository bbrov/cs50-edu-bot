# states.py
from aiogram.fsm.state import State, StatesGroup


class SolveTaskState(StatesGroup):
    waiting_for_answer = State()