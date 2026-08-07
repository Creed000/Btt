from typing import TypedDict


class PlanConfig(TypedDict):
    title: str
    price: int
    masters: int
    branches: int
    description: str


PLAN_CATALOG: dict[str, PlanConfig] = {
    "free": {
        "title": "Free",
        "price": 0,
        "masters": 1,
        "branches": 1,
        "description": "Для знакомства с сервисом",
    },
    "basic": {
        "title": "Basic",
        "price": 990,
        "masters": 3,
        "branches": 1,
        "description": "Для небольшого салона",
    },
    "pro": {
        "title": "Pro",
        "price": 2490,
        "masters": 10,
        "branches": 3,
        "description": "Для растущего бизнеса",
    },
    "business": {
        "title": "Business",
        "price": 4990,
        "masters": 50,
        "branches": 10,
        "description": "Для сети салонов",
    },
}


DEFAULT_PLAN_CODE = "free"


def get_plan(
    plan_code: str | None,
) -> PlanConfig:
    if not plan_code:
        return PLAN_CATALOG[DEFAULT_PLAN_CODE]

    return PLAN_CATALOG.get(
        plan_code,
        PLAN_CATALOG[DEFAULT_PLAN_CODE],
    )


def get_plan_title(
    plan_code: str | None,
) -> str:
    return get_plan(plan_code)["title"]


def get_plan_limits(
    plan_code: str | None,
) -> dict[str, int]:
    plan = get_plan(plan_code)

    return {
        "masters": plan["masters"],
        "branches": plan["branches"],
    }


def resolve_plan_code(
    plan_title: str,
) -> str | None:
    normalized = plan_title.strip().lower()

    for plan_code, plan in PLAN_CATALOG.items():
        if plan["title"].lower() == normalized:
            return plan_code

    return None
