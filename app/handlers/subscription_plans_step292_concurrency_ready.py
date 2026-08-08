from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.subscription_plan_request import (
    SubscriptionPlanRequest,
)
from app.models.user import User
from app.services.plan_catalog import (
    PLAN_CATALOG,
    get_plan_limits,
    get_plan_title,
    resolve_plan_code,
)
from app.services.subscription_limits import (
    count_salon_branches,
    count_salon_masters,
)


def _plan_value(
    plan,
    key: str,
    default,
):
    if isinstance(plan, dict):
        return plan.get(
            key,
            default,
        )

    return getattr(
        plan,
        key,
        default,
    )


def plans_menu(
    current_plan: str,
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for plan_code, plan in PLAN_CATALOG.items():
        title = _plan_value(
            plan,
            "title",
            plan_code.title(),
        )

        if plan_code == current_plan:
            button_text = (
                f"✅ Текущий тариф: {title}"
            )
        else:
            button_text = (
                f"💳 Выбрать тариф {title}"
            )

        keyboard.append(
            [KeyboardButton(button_text)]
        )

    keyboard.extend(
        [
            [KeyboardButton("🏢 Кабинет салона")],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите тариф",
    )


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
):
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


def _capacity_error(
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

    problems: list[str] = []

    if masters_count > limits["masters"]:
        problems.append(
            f"мастеров {masters_count}, "
            f"лимит {limits['masters']}"
        )

    if branches_count > limits["branches"]:
        problems.append(
            f"филиалов {branches_count}, "
            f"лимит {limits['branches']}"
        )

    if not problems:
        return None

    return (
        "Нельзя запросить этот тариф: "
        + "; ".join(problems)
        + ". Сначала уменьшите текущую нагрузку "
          "или выберите более высокий тариф."
    )


async def show_available_plans(
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
                "❌ Пользователь не найден.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

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

        masters_count = count_salon_masters(
            db,
            salon.id,
        )
        branches_count = count_salon_branches(
            db,
            salon.id,
        )

        pending_request = db.scalar(
            select(
                SubscriptionPlanRequest
            )
            .where(
                SubscriptionPlanRequest.salon_id
                == salon.id,
                SubscriptionPlanRequest.status
                == "pending",
            )
            .order_by(
                SubscriptionPlanRequest.id.desc()
            )
            .limit(1)
        )

        lines = [
            "💳 Тарифы GlowFlow",
            "",
            f"Текущий тариф: "
            f"{get_plan_title(salon.plan)}",
            f"Мастеров сейчас: {masters_count}",
            f"Филиалов сейчас: {branches_count}",
        ]

        if pending_request is not None:
            lines.extend(
                [
                    "",
                    "🕓 Уже есть запрос:",
                    f"#{pending_request.id} → "
                    f"{get_plan_title(pending_request.requested_plan)}",
                ]
            )

        lines.append("")

        for plan_code, plan in PLAN_CATALOG.items():
            title = _plan_value(
                plan,
                "title",
                plan_code.title(),
            )
            price = _plan_value(
                plan,
                "price",
                0,
            )
            description = _plan_value(
                plan,
                "description",
                "",
            )
            limits = get_plan_limits(
                plan_code
            )

            marker = (
                "✅"
                if plan_code == salon.plan
                else "▫️"
            )

            lines.extend(
                [
                    f"{marker} {title} — "
                    f"{price} сом/мес.",
                    f"Мастеров: до "
                    f"{limits['masters']}",
                    f"Филиалов: до "
                    f"{limits['branches']}",
                ]
            )

            if description:
                lines.append(
                    str(description)
                )

            lines.append("")

        await update.message.reply_text(
            "\n".join(lines).strip(),
            reply_markup=plans_menu(
                salon.plan
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось загрузить тарифы.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def request_plan_change(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    plan_title: str,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    selected_code = resolve_plan_code(
        plan_title
    )

    if (
        selected_code is None
        or selected_code not in PLAN_CATALOG
    ):
        await update.message.reply_text(
            "❌ Тариф не найден."
        )
        return

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id
                == update.effective_user.id
            )
        )

        if (
            user is None
            or not user.is_active
        ):
            salon = None
        else:
            # PostgreSQL: сериализуем два почти
            # одновременных запроса одного салона.
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
                .with_for_update()
            )

        if (
            user is None
            or salon is None
        ):
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        if salon.plan == selected_code:
            await update.message.reply_text(
                "ℹ️ Этот тариф уже подключён.",
                reply_markup=plans_menu(
                    salon.plan
                ),
            )
            return

        capacity_error = _capacity_error(
            db,
            salon,
            selected_code,
        )

        if capacity_error:
            await update.message.reply_text(
                f"⛔ {capacity_error}",
                reply_markup=plans_menu(
                    salon.plan
                ),
            )
            return

        existing_request = db.scalar(
            select(
                SubscriptionPlanRequest
            )
            .where(
                SubscriptionPlanRequest.salon_id
                == salon.id,
                SubscriptionPlanRequest.status
                == "pending",
            )
            .order_by(
                SubscriptionPlanRequest.id.desc()
            )
            .limit(1)
        )

        if existing_request is not None:
            if (
                existing_request.requested_plan
                == selected_code
            ):
                await update.message.reply_text(
                    "ℹ️ Такой запрос уже ожидает "
                    "обработки администратором.",
                    reply_markup=plans_menu(
                        salon.plan
                    ),
                )
                return

            existing_request.status = "replaced"
            db.add(existing_request)

            # UPDATE старого pending должен попасть
            # в БД до INSERT нового pending.
            db.flush()

        request = SubscriptionPlanRequest(
            salon_id=salon.id,
            requested_by_user_id=user.id,
            current_plan=salon.plan,
            requested_plan=selected_code,
            status="pending",
        )

        db.add(request)
        db.flush()

        request_id = request.id
        db.commit()

        title = get_plan_title(
            selected_code
        )
        plan = PLAN_CATALOG[
            selected_code
        ]
        price = _plan_value(
            plan,
            "price",
            0,
        )

        # Telegram-уведомление — дополнительный канал.
        # Сам запрос уже надёжно сохранён в PostgreSQL.
        for admin_id in settings.all_platform_admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "💳 Новый запрос на смену тарифа\n\n"
                        f"Запрос: #{request_id}\n"
                        f"Салон: {salon.name} "
                        f"(ID {salon.id})\n"
                        f"Владелец: "
                        f"{user.first_name or user.telegram_id}\n"
                        f"Текущий: "
                        f"{get_plan_title(salon.plan)}\n"
                        f"Запрошен: {title}\n"
                        f"Стоимость: {price} сом/мес."
                    ),
                )
            except Exception:
                # Запрос уже в БД, поэтому ошибка Telegram
                # не должна отменять его создание.
                pass

        await update.message.reply_text(
            "✅ Запрос на смену тарифа сохранён.\n\n"
            f"Номер запроса: #{request_id}\n"
            f"Салон: {salon.name}\n"
            f"Новый тариф: {title}\n"
            f"Стоимость: {price} сом/мес.\n\n"
            "Запрос сохранён в системе и не пропадёт "
            "после перезапуска Railway.",
            reply_markup=plans_menu(
                salon.plan
            ),
        )

    except IntegrityError:
        db.rollback()

        # Страховка уникального индекса из шага 291.
        # Вместо SQL-ошибки возвращаем пользователю
        # уже существующий pending-запрос.
        try:
            user, salon = get_owner_and_salon(
                db,
                update.effective_user.id,
            )

            pending_request = None

            if salon is not None:
                pending_request = db.scalar(
                    select(
                        SubscriptionPlanRequest
                    )
                    .where(
                        SubscriptionPlanRequest.salon_id
                        == salon.id,
                        SubscriptionPlanRequest.status
                        == "pending",
                    )
                    .order_by(
                        SubscriptionPlanRequest.id.desc()
                    )
                    .limit(1)
                )

            if (
                salon is not None
                and pending_request is not None
            ):
                await update.message.reply_text(
                    "ℹ️ Запрос на смену тарифа уже "
                    "сохранён и ожидает обработки.\n\n"
                    f"Запрос: #{pending_request.id}\n"
                    "Тариф: "
                    f"{get_plan_title(pending_request.requested_plan)}",
                    reply_markup=plans_menu(
                        salon.plan
                    ),
                )
            else:
                await update.message.reply_text(
                    "❌ Не удалось сохранить запрос. "
                    "Попробуйте ещё раз.",
                    reply_markup=user_main_menu(
                        db,
                        user,
                        update.effective_user.id,
                    ),
                )

        except Exception:
            db.rollback()

            await update.message.reply_text(
                "❌ Не удалось сохранить запрос "
                "на смену тарифа.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось сохранить запрос "
            "на смену тарифа.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()
