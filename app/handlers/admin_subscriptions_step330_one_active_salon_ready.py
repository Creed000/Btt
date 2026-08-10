from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.session import SessionLocal
from app.handlers.admin_panel import admin_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.subscription_plan_request import SubscriptionPlanRequest
from app.models.user import User
from app.services.access_control import can_manage_platform
from app.services.plan_catalog import (
    PLAN_CATALOG,
    get_plan,
    get_plan_limits,
    get_plan_title,
)
from app.services.subscription_limits import (
    count_salon_branches,
    count_salon_masters,
)
from app.services.timezone import local_naive_now


SUBSCRIPTION_DAYS = 30
LIST_LIMIT = 50


def salon_subscription_actions_menu(
    salons: list[Salon],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for salon in salons:
        keyboard.append(
            [
                KeyboardButton(
                    f"💳 Управлять салоном #{salon.id}"
                )
            ]
        )

    keyboard.extend(
        [
            [KeyboardButton("📨 Запросы на тариф")],
            [KeyboardButton("👑 Админ-панель")],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите салон",
    )


def salon_plan_menu(
    salon_id: int,
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for plan_code, plan in PLAN_CATALOG.items():
        title = (
            plan.get("title")
            if isinstance(plan, dict)
            else getattr(plan, "title", None)
        ) or plan_code.title()

        keyboard.append(
            [
                KeyboardButton(
                    f"✅ Активировать {title} "
                    f"для салона #{salon_id}"
                )
            ]
        )

    keyboard.extend(
        [
            [
                KeyboardButton(
                    f"⛔ Отключить подписку "
                    f"салона #{salon_id}"
                )
            ],
            [KeyboardButton("👑 Админ-панель")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите тариф",
    )


def get_platform_admin(
    db,
    telegram_id: int,
) -> User | None:
    user = db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    if not can_manage_platform(user):
        return None

    return user


async def deny_access(
    update: Update,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    await update.message.reply_text(
        "⛔ У вас нет доступа к управлению "
        "подписками SaaS.",
        reply_markup=admin_menu(),
    )


def _plan_capacity_error(
    db,
    salon: Salon,
    plan_code: str,
) -> str | None:
    limits = get_plan_limits(
        plan_code
    )

    masters_count = count_salon_masters(
        db,
        salon.id,
    )

    branches_count = count_salon_branches(
        db,
        salon.id,
    )

    max_masters = limits["masters"]
    max_branches = limits["branches"]

    problems: list[str] = []

    if masters_count > max_masters:
        problems.append(
            f"мастеров {masters_count}, "
            f"лимит тарифа {max_masters}"
        )

    if branches_count > max_branches:
        problems.append(
            f"филиалов {branches_count}, "
            f"лимит тарифа {max_branches}"
        )

    if not problems:
        return None

    return (
        "Нельзя активировать этот тариф: "
        + "; ".join(problems)
        + ". Сначала уменьшите количество "
          "мастеров/филиалов либо выберите "
          "более высокий тариф."
    )


def _lock_salon_for_activation(
    db,
    salon_id: int,
) -> tuple[Salon | None, Salon | None]:
    """
    Сериализует активацию салонов одного владельца.

    Возвращает:
    (target_salon, other_active_salon)

    Порядок блокировок:
    1. читаем target, чтобы узнать owner_id;
    2. блокируем User-владельца;
    3. повторно блокируем target Salon;
    4. проверяем другой активный Salon того же владельца.

    Благодаря блокировке User два разных салона одного owner
    нельзя активировать конкурентно в двух транзакциях.
    """
    preview = db.scalar(
        select(Salon).where(
            Salon.id == salon_id
        )
    )

    if preview is None:
        return None, None

    owner = db.scalar(
        select(User)
        .where(
            User.id == preview.owner_id
        )
        .with_for_update()
    )

    if owner is None:
        return None, None

    salon = db.scalar(
        select(Salon)
        .where(
            Salon.id == salon_id,
            Salon.owner_id == owner.id,
        )
        .with_for_update()
    )

    if salon is None:
        return None, None

    other_active = db.scalar(
        select(Salon)
        .where(
            Salon.owner_id == owner.id,
            Salon.is_active.is_(True),
            Salon.id != salon.id,
        )
        .order_by(Salon.id.asc())
        .limit(1)
    )

    return salon, other_active


async def show_salons_for_subscription(
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
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        salons = list(
            db.scalars(
                select(Salon)
                .options(
                    joinedload(Salon.owner)
                )
                .order_by(
                    Salon.id.desc()
                )
                .limit(LIST_LIMIT)
            ).unique().all()
        )

        total_count = len(
            list(
                db.scalars(
                    select(Salon.id)
                ).all()
            )
        )

        lines = [
            "💳 Подписки салонов",
            "",
            f"Всего салонов: {total_count}",
        ]

        if total_count > LIST_LIMIT:
            lines.append(
                f"Показаны последние {LIST_LIMIT}."
            )

        if not salons:
            lines.extend(
                [
                    "",
                    "Салонов пока нет.",
                ]
            )
        else:
            for salon in salons:
                owner_name = (
                    salon.owner.first_name
                    if salon.owner
                    and salon.owner.first_name
                    else "—"
                )

                plan_title = get_plan_title(
                    salon.plan
                )

                end_date = (
                    salon.subscription_ends_at.strftime(
                        "%d.%m.%Y %H:%M"
                    )
                    if salon.subscription_ends_at
                    else "—"
                )

                trial_end = (
                    salon.trial_ends_at.strftime(
                        "%d.%m.%Y %H:%M"
                    )
                    if salon.trial_ends_at
                    else "—"
                )

                masters_count = (
                    count_salon_masters(
                        db,
                        salon.id,
                    )
                )

                branches_count = (
                    count_salon_branches(
                        db,
                        salon.id,
                    )
                )

                limits = get_plan_limits(
                    salon.plan
                )

                lines.extend(
                    [
                        "",
                        f"ID салона: {salon.id}",
                        f"Название: {salon.name}",
                        f"Владелец: {owner_name}",
                        f"Тариф: {plan_title}",
                        f"Статус: {salon.subscription_status}",
                        f"Trial до: {trial_end}",
                        f"Подписка до: {end_date}",
                        "Активен: "
                        f"{'✅ да' if salon.is_active else '❌ нет'}",
                        "Мастера: "
                        f"{masters_count}/{limits['masters']}",
                        "Филиалы: "
                        f"{branches_count}/{limits['branches']}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=salon_subscription_actions_menu(
                salons
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось загрузить подписки салонов.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def open_salon_subscription_control(
    update: Update,
    salon_id: int,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        salon = db.scalar(
            select(Salon).where(
                Salon.id == salon_id
            )
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Салон не найден.",
                reply_markup=admin_menu(),
            )
            return

        plan = get_plan(
            salon.plan
        )
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

        await update.message.reply_text(
            "💳 Управление подпиской\n\n"
            f"Салон: {salon.name}\n"
            f"Текущий тариф: "
            f"{get_plan_title(salon.plan)}\n"
            f"Статус: {salon.subscription_status}\n"
            f"Мастера: "
            f"{masters_count}/{limits['masters']}\n"
            f"Филиалы: "
            f"{branches_count}/{limits['branches']}\n\n"
            "Выберите действие:",
            reply_markup=salon_plan_menu(
                salon.id
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось открыть управление подпиской.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def activate_salon_plan(
    update: Update,
    salon_id: int,
    plan_code: str,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    if plan_code not in PLAN_CATALOG:
        await update.message.reply_text(
            "❌ Неизвестный тариф.",
            reply_markup=admin_menu(),
        )
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        salon, other_active = _lock_salon_for_activation(
            db,
            salon_id,
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Салон или его владелец не найден.",
                reply_markup=admin_menu(),
            )
            return

        if other_active is not None:
            await update.message.reply_text(
                "⛔ Нельзя активировать этот салон.\n\n"
                f"У владельца уже есть активный салон "
                f"#{other_active.id} «{other_active.name}».\n"
                "Сначала отключите другой салон.",
                reply_markup=admin_menu(),
            )
            return

        capacity_error = _plan_capacity_error(
            db,
            salon,
            plan_code,
        )

        if capacity_error:
            await update.message.reply_text(
                f"⛔ {capacity_error}",
                reply_markup=salon_plan_menu(
                    salon.id
                ),
            )
            return

        now = local_naive_now()

        salon.plan = plan_code
        salon.subscription_status = "active"
        salon.subscription_ends_at = (
            now
            + timedelta(
                days=SUBSCRIPTION_DAYS
            )
        )
        salon.is_active = True
        salon.updated_at = now

        db.add(salon)
        db.commit()

        await update.message.reply_text(
            "✅ Подписка активирована.\n\n"
            f"Салон: {salon.name}\n"
            f"Тариф: "
            f"{get_plan_title(plan_code)}\n"
            "Активна до: "
            f"{salon.subscription_ends_at.strftime('%d.%m.%Y %H:%M')}",
            reply_markup=admin_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось активировать подписку.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def disable_salon_subscription(
    update: Update,
    salon_id: int,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        # Все изменения тарифа сериализуем по строке Salon.
        # Ту же блокировку использует включение мастера,
        # создание филиала и принятие приглашения.
        salon = db.scalar(
            select(Salon)
            .where(
                Salon.id == salon_id
            )
            .with_for_update()
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Салон не найден.",
                reply_markup=admin_menu(),
            )
            return

        now = local_naive_now()

        salon.subscription_status = "cancelled"
        salon.subscription_ends_at = now
        salon.updated_at = now

        # booking_enabled не меняем:
        # отключённая подписка сама блокирует каталог
        # и новые записи, а личная настройка мастера
        # должна сохраниться для будущего продления.
        db.add(salon)
        db.commit()

        await update.message.reply_text(
            "⛔ Подписка отключена.\n\n"
            f"Салон: {salon.name}\n"
            "Новые записи салона заблокированы подпиской. "
            "Личные настройки мастеров сохранены.",
            reply_markup=admin_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось отключить подписку.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


def pending_plan_requests_menu(
    requests: list[SubscriptionPlanRequest],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for request in requests:
        keyboard.append(
            [
                KeyboardButton(
                    f"✅ Одобрить запрос #{request.id}"
                )
            ]
        )
        keyboard.append(
            [
                KeyboardButton(
                    f"❌ Отклонить запрос #{request.id}"
                )
            ]
        )

    keyboard.extend(
        [
            [KeyboardButton("💳 Подписки салонов")],
            [KeyboardButton("👑 Админ-панель")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Запросы на тариф",
    )


async def show_pending_plan_requests(
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
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        requests = list(
            db.scalars(
                select(SubscriptionPlanRequest)
                .options(
                    joinedload(
                        SubscriptionPlanRequest.salon
                    ),
                    joinedload(
                        SubscriptionPlanRequest.requested_by
                    ),
                )
                .where(
                    SubscriptionPlanRequest.status
                    == "pending"
                )
                .order_by(
                    SubscriptionPlanRequest.id.asc()
                )
                .limit(50)
            ).unique().all()
        )

        lines = [
            "📨 Запросы на смену тарифа",
            "",
            f"Ожидают обработки: {len(requests)}",
        ]

        if not requests:
            lines.extend(
                [
                    "",
                    "Новых запросов нет.",
                ]
            )
        else:
            for request in requests:
                salon = request.salon
                requester = request.requested_by

                salon_name = (
                    salon.name
                    if salon is not None
                    else f"Салон #{request.salon_id}"
                )

                owner_name = (
                    requester.first_name
                    if requester is not None
                    and requester.first_name
                    else "—"
                )

                lines.extend(
                    [
                        "",
                        f"Запрос #{request.id}",
                        f"Салон: {salon_name}",
                        f"Владелец: {owner_name}",
                        "Текущий тариф: "
                        f"{get_plan_title(request.current_plan)}",
                        "Запрошен: "
                        f"{get_plan_title(request.requested_plan)}",
                        "Создан: "
                        f"{request.created_at.strftime('%d.%m.%Y %H:%M')}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=pending_plan_requests_menu(
                requests
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось загрузить запросы на тариф.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def approve_plan_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request_id: int,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        # Сначала читаем request_id/salon_id без блокировки,
        # затем блокируем Salon, и только после этого сам запрос.
        # Такой порядок совпадает с owner-flow и снижает риск deadlock.
        request = db.scalar(
            select(SubscriptionPlanRequest)
            .options(
                joinedload(
                    SubscriptionPlanRequest.requested_by
                ),
            )
            .where(
                SubscriptionPlanRequest.id == request_id
            )
        )

        if request is None:
            await update.message.reply_text(
                "❌ Запрос не найден.",
                reply_markup=admin_menu(),
            )
            return

        salon, other_active = _lock_salon_for_activation(
            db,
            request.salon_id,
        )

        # После получения блокировки владельца/салона повторно
        # блокируем и перечитываем сам запрос: его мог обработать
        # другой администратор.
        request = db.scalar(
            select(SubscriptionPlanRequest)
            .options(
                joinedload(
                    SubscriptionPlanRequest.requested_by
                ),
            )
            .where(
                SubscriptionPlanRequest.id == request_id
            )
            .with_for_update()
        )

        if request is None:
            await update.message.reply_text(
                "❌ Запрос больше не существует.",
                reply_markup=admin_menu(),
            )
            return

        if request.status != "pending":
            await update.message.reply_text(
                f"ℹ️ Запрос #{request.id} уже обработан "
                f"(статус: {request.status}).",
                reply_markup=admin_menu(),
            )
            return

        if salon is None:
            request.status = "rejected"
            request.resolved_at = local_naive_now()
            db.add(request)
            db.commit()

            await update.message.reply_text(
                "❌ Салон запроса или его владелец больше "
                "не существует. Запрос закрыт.",
                reply_markup=admin_menu(),
            )
            return

        if other_active is not None:
            await update.message.reply_text(
                f"⛔ Запрос #{request.id} пока нельзя одобрить.\n\n"
                f"У владельца уже есть активный салон "
                f"#{other_active.id} «{other_active.name}».\n"
                "Сначала отключите другой салон.",
                reply_markup=pending_plan_requests_menu(
                    [request]
                ),
            )
            return

        if request.requested_plan not in PLAN_CATALOG:
            request.status = "rejected"
            request.resolved_at = local_naive_now()
            db.add(request)
            db.commit()

            await update.message.reply_text(
                "❌ Запрошенный тариф больше не существует. "
                "Запрос закрыт.",
                reply_markup=admin_menu(),
            )
            return

        capacity_error = _plan_capacity_error(
            db,
            salon,
            request.requested_plan,
        )

        if capacity_error:
            await update.message.reply_text(
                f"⛔ Запрос #{request.id} пока нельзя одобрить.\n\n"
                f"{capacity_error}",
                reply_markup=pending_plan_requests_menu(
                    [request]
                ),
            )
            return

        now = local_naive_now()

        salon.plan = request.requested_plan
        salon.subscription_status = "active"
        salon.subscription_ends_at = (
            now + timedelta(days=SUBSCRIPTION_DAYS)
        )
        salon.is_active = True
        salon.updated_at = now

        request.status = "approved"
        request.resolved_at = now

        db.add(salon)
        db.add(request)
        db.commit()

        owner_telegram_id = (
            request.requested_by.telegram_id
            if request.requested_by is not None
            else None
        )

        plan_title = get_plan_title(
            request.requested_plan
        )

        await update.message.reply_text(
            "✅ Запрос одобрен.\n\n"
            f"Запрос: #{request.id}\n"
            f"Салон: {salon.name}\n"
            f"Тариф: {plan_title}\n"
            "Активен до: "
            f"{salon.subscription_ends_at.strftime('%d.%m.%Y %H:%M')}",
            reply_markup=admin_menu(),
        )

        if owner_telegram_id is not None:
            try:
                await context.bot.send_message(
                    chat_id=owner_telegram_id,
                    text=(
                        "✅ Ваш запрос на смену тарифа одобрен.\n\n"
                        f"Салон: {salon.name}\n"
                        f"Тариф: {plan_title}\n"
                        "Активен до: "
                        f"{salon.subscription_ends_at.strftime('%d.%m.%Y %H:%M')}"
                    ),
                )
            except Exception:
                pass

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось одобрить запрос.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def reject_plan_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request_id: int,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        request = db.scalar(
            select(SubscriptionPlanRequest)
            .options(
                joinedload(
                    SubscriptionPlanRequest.salon
                ),
                joinedload(
                    SubscriptionPlanRequest.requested_by
                ),
            )
            .where(
                SubscriptionPlanRequest.id == request_id
            )
            .with_for_update()
        )

        if request is None:
            await update.message.reply_text(
                "❌ Запрос не найден.",
                reply_markup=admin_menu(),
            )
            return

        if request.status != "pending":
            await update.message.reply_text(
                f"ℹ️ Запрос #{request.id} уже обработан "
                f"(статус: {request.status}).",
                reply_markup=admin_menu(),
            )
            return

        request.status = "rejected"
        request.resolved_at = local_naive_now()
        db.add(request)
        db.commit()

        salon_name = (
            request.salon.name
            if request.salon is not None
            else f"Салон #{request.salon_id}"
        )

        plan_title = get_plan_title(
            request.requested_plan
        )

        await update.message.reply_text(
            "❌ Запрос отклонён.\n\n"
            f"Запрос: #{request.id}\n"
            f"Салон: {salon_name}\n"
            f"Тариф: {plan_title}",
            reply_markup=admin_menu(),
        )

        if request.requested_by is not None:
            try:
                await context.bot.send_message(
                    chat_id=request.requested_by.telegram_id,
                    text=(
                        "❌ Ваш запрос на смену тарифа отклонён.\n\n"
                        f"Салон: {salon_name}\n"
                        f"Тариф: {plan_title}"
                    ),
                )
            except Exception:
                pass

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось отклонить запрос.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def admin_subscription_requests_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.message.text is None
    ):
        return

    text_value = update.message.text.strip()

    if text_value == "📨 Запросы на тариф":
        await show_pending_plan_requests(
            update,
            context,
        )
        return

    approve_prefix = "✅ Одобрить запрос #"

    if text_value.startswith(
        approve_prefix
    ):
        raw_id = text_value.removeprefix(
            approve_prefix
        ).strip()

        if raw_id.isdigit():
            await approve_plan_request(
                update,
                context,
                int(raw_id),
            )
        return

    reject_prefix = "❌ Отклонить запрос #"

    if text_value.startswith(
        reject_prefix
    ):
        raw_id = text_value.removeprefix(
            reject_prefix
        ).strip()

        if raw_id.isdigit():
            await reject_plan_request(
                update,
                context,
                int(raw_id),
            )
        return


admin_subscription_requests_handler = MessageHandler(
    filters.Regex(
        r"^(📨 Запросы на тариф|"
        r"✅ Одобрить запрос #[0-9]+|"
        r"❌ Отклонить запрос #[0-9]+)$"
    ),
    admin_subscription_requests_router,
)
