from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.subscription_plan_request import (
    SubscriptionPlanRequest,
)
from app.models.user import User
from app.services.master_catalog import (
    available_masters_query,
)
from app.services.plan_catalog import (
    get_plan_limits,
    get_plan_title,
)
from app.services.subscription_limits import (
    count_salon_branches,
    count_salon_masters,
)
from app.services.timezone import local_naive_now


def salon_owner_menu(
    branches: list | None = None,
) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🏢 Мой салон")],
        [KeyboardButton("🏬 Мои филиалы")],
        [KeyboardButton("👥 Мастера салона")],
        [KeyboardButton("➕ Добавить филиал")],
        [KeyboardButton("➕ Добавить мастера")],
        [KeyboardButton("🏬 Назначить филиал мастеру")],
        [KeyboardButton("💳 Тариф и подписка")],
    ]

    if branches is not None and len(branches) > 1:
        for branch in branches:
            keyboard.append(
                [
                    KeyboardButton(
                        f"🗑 Удалить филиал #{branch.id}"
                    )
                ]
            )

    keyboard.append(
        [KeyboardButton("⬅️ Назад")]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Кабинет владельца",
    )


def subscription_status_text(
    salon: Salon,
) -> str:
    status_names = {
        "trial": "Пробный период",
        "active": "Активна",
        "expired": "Истекла",
        "cancelled": "Отменена",
    }

    status = status_names.get(
        salon.subscription_status,
        salon.subscription_status,
    )

    now = local_naive_now()

    if (
        salon.subscription_status == "trial"
        and salon.trial_ends_at is not None
    ):
        remaining = (
            salon.trial_ends_at - now
        )

        if remaining.total_seconds() <= 0:
            return (
                "Истекла\n"
                "Пробный период завершён"
            )

        days = max(
            remaining.days,
            0,
        )

        return (
            f"{status}\n"
            f"Осталось дней: {days}\n"
            "До: "
            f"{salon.trial_ends_at.strftime('%d.%m.%Y %H:%M')}"
        )

    if (
        salon.subscription_status == "active"
        and salon.subscription_ends_at is not None
    ):
        if salon.subscription_ends_at <= now:
            return (
                "Истекла\n"
                "Подписка завершена"
            )

        return (
            f"{status}\n"
            "До: "
            f"{salon.subscription_ends_at.strftime('%d.%m.%Y %H:%M')}"
        )

    if salon.subscription_ends_at is not None:
        return (
            f"{status}\n"
            "До: "
            f"{salon.subscription_ends_at.strftime('%d.%m.%Y %H:%M')}"
        )

    return status


def get_owner_and_salon(
    db,
    telegram_id: int,
) -> tuple[User | None, Salon | None]:
    user = db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    if (
        user is None
        or not user.is_active
    ):
        return user, None

    salon = db.scalar(
        select(Salon)
        .where(
            Salon.owner_id == user.id,
            Salon.is_active.is_(True),
        )
        .order_by(
            Salon.id.asc()
        )
        .limit(1)
    )

    return user, salon


def user_main_menu(
    db,
    user: User | None,
    telegram_id: int,
) -> ReplyKeyboardMarkup:
    if user is None:
        return main_menu(
            telegram_id=telegram_id,
        )

    has_salon = (
        db.scalar(
            select(Salon.id)
            .where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
            .limit(1)
        )
        is not None
    )

    has_master = (
        db.scalar(
            select(Master.id)
            .where(
                Master.user_id == user.id
            )
            .limit(1)
        )
        is not None
    )

    return main_menu(
        role=user.role,
        telegram_id=telegram_id,
        has_salon=has_salon,
        has_master=has_master,
    )


def get_pending_plan_request(
    db,
    salon_id: int,
) -> SubscriptionPlanRequest | None:
    return db.scalar(
        select(
            SubscriptionPlanRequest
        )
        .where(
            SubscriptionPlanRequest.salon_id
            == salon_id,
            SubscriptionPlanRequest.status
            == "pending",
        )
        .order_by(
            SubscriptionPlanRequest.id.desc()
        )
        .limit(1)
    )


def pending_request_text(
    request: SubscriptionPlanRequest | None,
) -> str:
    if request is None:
        return "Нет"

    return (
        f"#{request.id} → "
        f"{get_plan_title(request.requested_plan)} "
        "(ожидает решения)"
    )


async def open_salon_dashboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        user, salon = get_owner_and_salon(
            db,
            update.effective_user.id,
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. "
                "Отправьте /start.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        if salon is None:
            await update.message.reply_text(
                "У вас пока нет активного салона.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        salon = db.scalar(
            select(Salon)
            .options(
                joinedload(
                    Salon.branches
                )
            )
            .where(
                Salon.id == salon.id
            )
        )

        if salon is None:
            raise ValueError(
                "Салон не найден."
            )

        masters_count = count_salon_masters(
            db,
            salon.id,
        )
        branches_count = count_salon_branches(
            db,
            salon.id,
        )

        limits = get_plan_limits(
            salon.plan
        )

        available_master_ids = {
            master.id
            for master in db.scalars(
                available_masters_query()
                .where(
                    Master.salon_id
                    == salon.id
                )
            ).unique().all()
        }

        pending_request = (
            get_pending_plan_request(
                db,
                salon.id,
            )
        )

        await update.message.reply_text(
            "🏢 Кабинет салона\n\n"
            f"ID: {salon.id}\n"
            f"Название: {salon.name}\n"
            f"Slug: {salon.slug}\n"
            f"Город: {salon.city or '—'}\n"
            f"Адрес: {salon.address or '—'}\n"
            f"Телефон: {salon.phone or '—'}\n\n"
            f"🏬 Филиалы: "
            f"{branches_count}/{limits['branches']}\n"
            f"👥 Мастера: "
            f"{masters_count}/{limits['masters']}\n"
            f"📅 Доступны клиентам: "
            f"{len(available_master_ids)}\n\n"
            f"💳 Тариф: "
            f"{get_plan_title(salon.plan)}\n"
            "Подписка:\n"
            f"{subscription_status_text(salon)}\n\n"
            "📨 Запрос тарифа: "
            f"{pending_request_text(pending_request)}",
            reply_markup=salon_owner_menu(),
        )

    except ValueError as error:
        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=user_main_menu(
                db,
                user if "user" in locals() else None,
                update.effective_user.id,
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось открыть кабинет салона.",
            reply_markup=user_main_menu(
                db,
                user if "user" in locals() else None,
                update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def show_salon_branches(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        user, salon = get_owner_and_salon(
            db,
            update.effective_user.id,
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        salon = db.scalar(
            select(Salon)
            .options(
                joinedload(
                    Salon.branches
                )
            )
            .where(
                Salon.id == salon.id
            )
        )

        lines = [
            "🏬 Мои филиалы"
        ]

        if (
            salon is None
            or not salon.branches
        ):
            lines.extend(
                [
                    "",
                    "Филиалов пока нет.",
                ]
            )
        else:
            for branch in salon.branches:
                lines.extend(
                    [
                        "",
                        f"№{branch.id}",
                        f"Название: {branch.name}",
                        f"Адрес: {branch.address}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=salon_owner_menu(
                salon.branches
                if salon is not None
                else []
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось загрузить филиалы.",
            reply_markup=user_main_menu(
                db,
                user if "user" in locals() else None,
                update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def show_salon_masters(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        user, salon = get_owner_and_salon(
            db,
            update.effective_user.id,
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        masters = list(
            db.scalars(
                select(Master)
                .options(
                    joinedload(
                        Master.user
                    ),
                    joinedload(
                        Master.branch
                    ),
                )
                .where(
                    Master.salon_id
                    == salon.id
                )
                .order_by(
                    Master.id
                )
            ).unique().all()
        )

        available_master_ids = {
            master.id
            for master in db.scalars(
                available_masters_query()
                .where(
                    Master.salon_id
                    == salon.id
                )
            ).unique().all()
        }

        lines = [
            "👥 Мастера салона"
        ]

        if not masters:
            lines.extend(
                [
                    "",
                    "Мастеров пока нет.",
                ]
            )
        else:
            for master in masters:
                name = (
                    master.user.first_name
                    if master.user
                    and master.user.first_name
                    else "Без имени"
                )

                branch_name = (
                    master.branch.name
                    if master.branch
                    else "не назначен"
                )

                account_active = bool(
                    master.user
                    and master.user.is_active
                )

                lines.extend(
                    [
                        "",
                        f"ID мастера: {master.id}",
                        f"Имя: {name}",
                        f"Филиал: {branch_name}",
                        f"Рейтинг: "
                        f"{master.rating:.1f}",
                        "Аккаунт: "
                        f"{'✅ активен' if account_active else '⛔ отключён'}",
                        "Проверен: "
                        f"{'✅ да' if master.is_verified else '❌ нет'}",
                        "Переключатель записи: "
                        f"{'✅ включён' if master.booking_enabled else '⏸ выключен'}",
                        "Доступен клиентам: "
                        f"{'✅ да' if master.id in available_master_ids else '❌ нет'}",
                    ]
                )

        keyboard = [
            list(row)
            for row in salon_owner_menu().keyboard[:-1]
        ]

        for master in masters:
            if (
                master.user is not None
                and master.user.id == user.id
            ):
                continue

            keyboard.append(
                [
                    KeyboardButton(
                        f"🚪 Убрать мастера #{master.id}"
                    )
                ]
            )

        keyboard.append(
            [KeyboardButton("⬅️ Назад")]
        )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=ReplyKeyboardMarkup(
                keyboard=keyboard,
                resize_keyboard=True,
                one_time_keyboard=False,
                input_field_placeholder="Мастера салона",
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось загрузить мастеров салона.",
            reply_markup=user_main_menu(
                db,
                user if "user" in locals() else None,
                update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def show_salon_subscription(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        user, salon = get_owner_and_salon(
            db,
            update.effective_user.id,
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        limits = get_plan_limits(
            salon.plan
        )

        masters_count = count_salon_masters(
            db,
            salon.id,
        )

        branches_count = count_salon_branches(
            db,
            salon.id,
        )

        pending_request = (
            get_pending_plan_request(
                db,
                salon.id,
            )
        )

        await update.message.reply_text(
            "💳 Тариф и подписка\n\n"
            f"Текущий тариф: "
            f"{get_plan_title(salon.plan)}\n"
            "Статус:\n"
            f"{subscription_status_text(salon)}\n\n"
            f"👥 Мастера: "
            f"{masters_count}/{limits['masters']}\n"
            f"🏬 Филиалы: "
            f"{branches_count}/{limits['branches']}\n\n"
            "📨 Запрос на смену тарифа: "
            f"{pending_request_text(pending_request)}",
            reply_markup=salon_owner_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось загрузить подписку.",
            reply_markup=user_main_menu(
                db,
                user if "user" in locals() else None,
                update.effective_user.id,
            ),
        )

    finally:
        db.close()
