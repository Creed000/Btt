"""
Совместимый модуль для старых импортов.

Актуальная реализация фоновых напоминаний находится только в:
    app.services.booking_reminders

Не добавляйте сюда отдельную бизнес-логику, чтобы две версии
напоминаний больше не расходились.
"""

from app.services.booking_reminders import process_booking_reminders

__all__ = [
    "process_booking_reminders",
]
