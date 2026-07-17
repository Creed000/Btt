from aiogram.fsm.state import State, StatesGroup


class BookingState(StatesGroup):
    category = State()
    city = State()
    master = State()
    date = State()
    time = State()
    confirm = State()
