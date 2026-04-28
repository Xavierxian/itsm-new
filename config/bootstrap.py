import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv


def load_environment():
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(base_dir / ".env")


def ensure_mysql_database():
    load_environment()
    database = os.getenv("MYSQL_DB")
    if not database:
        return

    connection = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
            )
    finally:
        connection.close()


def ensure_schema():
    import django
    from django.core.management import call_command

    ensure_mysql_database()
    django.setup()
    call_command("migrate", interactive=False, verbosity=1, fake_initial=True)

