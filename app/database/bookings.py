from datetime import date, datetime, time, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.category import Category
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.booking_slot_validation import (
    validate_selected_booking_slot,
)
from app.services.master_catalog import master_is_available



ACTIVE_BOOKING_STATUSES = {
    "new",
    "confirmed",
}


BOOKING_SLOT_CONSTRAINTS = {
    "uq_bookings_active_master_slot",
    "uq_bookings_active_client_slot",
    "ex_bookings_active_master_overlap",
    "ex_bookings_active_client_overlap",
}


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    """Best-effort имя PostgreSQL constraint без привязки к одному драйверу."""
    original = getattr(exc, "orig", None)

    diag = getattr(original, "diag", None)
    constraint_name = getattr(
        diag,
        "constraint_name",
        None,
    )

    if constraint_name:
        return str(constraint_name)

    # psycopg/psycopg2 обычно дают diag, но оставляем fallback
    # на текст для совместимости с разными версиями драйвера.
    message = str(original or exc)

    for name in BOOKING_SLOT_CONSTRAINTS:
        if name in message:
            return name

    return None


def _intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return (
        first_start < second_end
        and second_start < first_end
    )


def _lock_client_day(
    db,
    client_id: int,
    booking_date: date,
) -> None:
    """
    На PostgreSQL сериализует создание записей
    одного клиента на одну дату.

    Используем отрицательное пространство ключей,
    чтобы оно не пересекалось с master-day lock.
    """
    bind = db.get_bind()

    if (
        bind is None
        or bind.dialect.name != "postgresql"
    ):
        return

    lock_key = -(
        int(client_id) * 10_000_000
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


def _validate_client_has_no_overlap(
    db,
    client_id: int,
    booking_date: date,
    booking_time: time,
    service_duration: int,
) -> None:
    """
    Клиент не может иметь две активные записи,
    пересекающиеся по времени, даже у разных мастеров.
    """
    selected_start = datetime.combine(
        booking_date,
        booking_time,
    )
    selected_end = (
        selected_start
        + timedelta(
            minutes=service_duration
        )
    )

    existing_bookings = list(
        db.scalars(
            select(Booking)
            .options(
                joinedload(Booking.service)
            )
            .where(
                Booking.client_id == client_id,
                Booking.booking_date
                == booking_date,
                Booking.status.in_(
                    ACTIVE_BOOKING_STATUSES
                ),
            )
            .order_by(
                Booking.booking_time
            )
        ).unique().all()
    )

    for existing in existing_bookings:
        existing_duration = existing.duration_minutes

        existing_start = datetime.combine(
            existing.booking_date,
            existing.booking_time,
        )
        existing_end = (
            existing_start
            + timedelta(
                minutes=existing_duration
            )
        )

        if _intervals_overlap(
            selected_start,
            selected_end,
            existing_start,
            existing_end,
        ):
            raise ValueError(
                "У вас уже есть другая запись, "
                "которая пересекается по времени. "
                "Выберите другое время."
            )

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
        client_preview = db.scalar(
            select(User).where(
                User.telegram_id == telegram_id
            )
        )

        if client_preview is None:
            raise ValueError(
                "Пользователь не зарегистрирован. "
                "Отправьте /start."
            )

        master_identity = db.execute(
            select(
                Master.user_id,
                Master.salon_id,
            ).where(
                Master.id == master_id
            )
        ).one_or_none()

        if master_identity is None:
            raise ValueError(
                "Мастер больше не существует."
            )

        master_user_id = master_identity.user_id
        master_salon_id = master_identity.salon_id

        # Статус аккаунта клиента и аккаунта мастера меняется
        # админом под User FOR UPDATE. Блокируем обе строки
        # в стабильном порядке по id, чтобы избежать deadlock.
        locked_users = {
            item.id: item
            for item in db.scalars(
                select(User)
                .where(
                    User.id.in_(
                        {
                            client_preview.id,
                            master_user_id,
                        }
                    )
                )
                .order_by(User.id)
                .with_for_update()
            ).all()
        }

        user = locked_users.get(
            client_preview.id
        )
        master_user = locked_users.get(
            master_user_id
        )

        if user is None:
            raise ValueError(
                "Пользователь больше не существует."
            )

        if not user.is_active:
            raise ValueError(
                "Ваш аккаунт временно отключён."
            )

        if master_user is None or not master_user.is_active:
            raise ValueError(
                "Аккаунт мастера временно недоступен."
            )

        # Сначала блокируем client+date, затем master+date.
        # Это защищает и клиента, и мастера от гонок
        # при почти одновременных подтверждениях.
        _lock_client_day(
            db,
            user.id,
            booking_date,
        )

        _lock_master_day(
            db,
            master_id,
            booking_date,
        )

        # Для мастера салона сначала блокируем Salon, затем Master.
        # Админские изменения подписки и salon-flow используют тот же
        # порядок Salon -> Master. Поэтому финальная проверка доступа
        # не может пройти на устаревшем состоянии подписки.
        if master_salon_id is not None:
            locked_salon_id = db.scalar(
                select(Salon.id)
                .where(
                    Salon.id == master_salon_id
                )
                .with_for_update()
            )

            if locked_salon_id is None:
                raise ValueError(
                    "Салон больше не существует."
                )

        # Недельное расписание изменяется под FOR UPDATE строки Master.
        # Берём тот же row-lock до финальной проверки слота, чтобы
        # create_booking() не мог пройти одновременно с изменением
        # рабочего дня/рабочих часов мастера.
        locked_master_id = db.scalar(
            select(Master.id)
            .where(
                Master.id == master_id
            )
            .with_for_update()
        )

        if locked_master_id is None:
            raise ValueError(
                "Мастер больше не существует."
            )

        current_master_identity = db.execute(
            select(
                Master.user_id,
                Master.salon_id,
            ).where(
                Master.id == master_id
            )
        ).one()

        if (
            current_master_identity.user_id != master_user_id
            or current_master_identity.salon_id != master_salon_id
        ):
            raise ValueError(
                "Профиль мастера изменился. "
                "Повторите выбор мастера."
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
            select(Service)
            .join(
                Category,
                Category.id == Service.category_id,
            )
            .where(
                Service.id == service_id,
                Service.master_id == master.id,
                Service.category_id.is_not(None),
                Service.duration > 0,
                Service.price >= 0,
            )
        )

        if service is None:
            raise ValueError(
                "Услуга больше недоступна у выбранного мастера."
            )

        _validate_client_has_no_overlap(
            db=db,
            client_id=user.id,
            booking_date=booking_date,
            booking_time=booking_time,
            service_duration=service.duration,
        )

        # На этом этапе service уже подтверждена как:
        # - принадлежащая выбранному мастеру;
        # - имеющая существующую категорию;
        # - имеющая корректные цену и длительность.
        #
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
            duration_minutes=service.duration,
            price_amount=service.price,
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

    except IntegrityError as exc:
        db.rollback()

        constraint_name = _integrity_constraint_name(
            exc
        )

        if constraint_name in BOOKING_SLOT_CONSTRAINTS:
            raise ValueError(
                "Это время уже занято или пересекается "
                "с другой активной записью. "
                "Выберите другой слот."
            ) from None

        # Не маскируем неизвестные ошибки целостности:
        # они должны попасть в лог/мониторинг как реальный дефект.
        raise

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
