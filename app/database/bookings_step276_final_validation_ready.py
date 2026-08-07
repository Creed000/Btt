from datetime import date, time

from sqlalchemy import select, text
from sqlalchemy.orm import joinedload

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.master import Master
from app.models.service import Service
from app.models.user import User
from app.services.booking_slot_validation import (
    validate_selected_booking_slot,
)
from app.services.master_catalog import master_is_available


def _lock_master_day(
    db,
    master_id: int,
    booking_date: date,
) -> None:
    """
    На PostgreSQL сериализует создание записей
    для одного мастера на одну дату.

    Это закрывает гонку:
    два клиента одновременно нажали подтверждение
    на один и тот же свободный слот.
    """
    bind = db.get_bind()

    if (
        bind is None
        or bind.dialect.name != "postgresql"
    ):
        return

    # Один bigint-ключ на master + date.
    lock_key = (
        int(master_id) * 10_000_000
        + booking_date.toordinal()
    )

    db.execute(
        text(
            "SELECT pg_advisory_xact_lock(:lock_key)"
        ),
        {
            "lock_key": lock_key,
        },
    )


def create_booking(
    telegram_id: int,
    master_id: int,
    service_id: int,
    booking_date: date,
    booking_time: time,
) -> Booking:
    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == telegram_id
            )
        )

        if user is None:
            raise ValueError(
                "Пользователь не зарегистрирован. "
                "Отправьте /start."
            )

        if not user.is_active:
            raise ValueError(
                "Ваш аккаунт временно отключён."
            )

        # В PostgreSQL блокируем master+date до конца
        # текущей транзакции, затем повторно проверяем слот.
        _lock_master_day(
            db,
            master_id,
            booking_date,
        )

        # Строгая финальная проверка мастера:
        # active user, verified, booking_enabled,
        # город, услуга, филиал и подписка салона.
        master = master_is_available(
            db,
            master_id,
        )

        if master is None:
            raise ValueError(
                "Мастер больше недоступен для записи. "
                "Выберите другого мастера."
            )

        service = db.scalar(
            select(Service).where(
                Service.id == service_id,
                Service.master_id == master.id,
                Service.duration > 0,
                Service.price >= 0,
            )
        )

        if service is None:
            raise ValueError(
                "Услуга больше недоступна у выбранного мастера."
            )

        # Повторная финальная проверка:
        # - дата входит в окно записи;
        # - день явно настроен рабочим;
        # - нет выходного;
        # - нет блокировки;
        # - слот ещё свободен;
        # - услуга целиком помещается в рабочее время.
        validate_selected_booking_slot(
            db=db,
            master_id=master.id,
            service_id=service.id,
            booking_date=booking_date,
            booking_time=booking_time,
        )

        booking = Booking(
            client_id=user.id,
            master_id=master.id,
            service_id=service.id,
            booking_date=booking_date,
            booking_time=booking_time,
            status="new",
        )

        db.add(booking)
        db.flush()

        booking_id = booking.id

        db.commit()

        loaded_booking = db.scalar(
            select(Booking)
            .options(
                joinedload(Booking.client),
                joinedload(Booking.master).joinedload(
                    Master.user
                ),
                joinedload(Booking.service),
            )
            .where(
                Booking.id == booking_id
            )
        )

        if loaded_booking is None:
            raise RuntimeError(
                "Созданная запись не найдена."
            )

        # Объект должен оставаться доступным после
        # закрытия SQLAlchemy-сессии.
        db.expunge_all()

        return loaded_booking

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
