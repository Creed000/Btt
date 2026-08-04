import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _test_environment(tmp_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "BOT_TOKEN": "123456:TEST_TOKEN",
            "DATABASE_URL": (
                f"sqlite:///{tmp_path / 'smoke_test.db'}"
            ),
            "APP_TIMEZONE": "Asia/Bishkek",
            "SECRET_KEY": "smoke-test-secret-key-12345",
            "PYTHONPATH": str(PROJECT_ROOT),
        }
    )
    return environment


def test_all_python_files_compile() -> None:
    python_files = list(
        (PROJECT_ROOT / "app").rglob("*.py")
    )

    assert python_files, "Python-файлы приложения не найдены"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            str(PROJECT_ROOT / "app"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        result.stdout + result.stderr
    )


def test_all_app_modules_import(
    tmp_path: Path,
) -> None:
    script = r"""
import importlib
import pkgutil

import app

errors = []

for module_info in pkgutil.walk_packages(
    app.__path__,
    prefix="app.",
):
    module_name = module_info.name

    try:
        importlib.import_module(module_name)
    except Exception as error:
        errors.append(
            f"{module_name}: "
            f"{type(error).__name__}: {error}"
        )

if errors:
    raise RuntimeError(
        "\n".join(errors)
    )
"""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
        ],
        cwd=PROJECT_ROOT,
        env=_test_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        result.stdout + result.stderr
    )


def test_database_schema_upgrade(
    tmp_path: Path,
) -> None:
    script = r"""
from sqlalchemy import inspect

from app.database.init_db import init_db
from app.database.schema_upgrade import (
    upgrade_database_schema,
)
from app.database.session import engine

init_db()
upgrade_database_schema()

tables = set(
    inspect(engine).get_table_names()
)

required_tables = {
    "users",
    "salons",
    "branches",
    "masters",
    "services",
    "bookings",
    "master_schedules",
    "master_days_off",
    "master_time_blocks",
}

missing = required_tables - tables

if missing:
    raise RuntimeError(
        "Не созданы таблицы: "
        + ", ".join(sorted(missing))
    )
"""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
        ],
        cwd=PROJECT_ROOT,
        env=_test_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        result.stdout + result.stderr
    )
