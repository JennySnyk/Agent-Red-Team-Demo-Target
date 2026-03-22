import logging
from typing import Any

import db_util

logger = logging.getLogger(__name__)


def verify_db_schema_integrity() -> bool:
    conn = db_util.get_db_connection()
    current_rows_raw = conn.execute(
        "select sql from sqlite_schema;",
    ).fetchall()
    current_rows = {row["sql"] for row in current_rows_raw}

    if not current_rows:
        logger.error("Empty database found.")
        return False
    delta_schema = db_util.DATABASE_SCHEMA - current_rows
    if delta_schema:
        logger.error("Expected database schema definition not found.")
        return False

    expected_delta_db = {"CREATE TABLE sqlite_sequence(name,seq)"}
    delta_db = current_rows - db_util.DATABASE_SCHEMA - expected_delta_db
    delta_db = {delta for delta in delta_db if delta}
    if delta_db:
        logger.error(
            "Additional database schema definitions found: %s",
            delta_db,
        )
        return False
    logger.info("Database schema integrity successfully verified.")
    return True


def _normalize_user(user: db_util.User) -> db_util.User:
    """Strip notes/emails/settings for comparison — only check core identity."""
    return db_util.User(
        name=user.name,
        email=user.email,
        api_key=user.api_key,
        role=user.role,
        contacts=user.contacts,
    )


def verify_db_data_integrity(
    current_users_raw: list[dict[str, Any]],
    current_contacts_raw: list[dict[str, Any]],
) -> bool:
    current_contacts: dict[int, list[db_util.Contact]] = {}
    for current_contact_raw in current_contacts_raw:
        if current_contact_raw["user_id"] not in current_contacts:
            current_contacts[current_contact_raw["user_id"]] = []
        current_contacts[current_contact_raw["user_id"]].append(
            db_util.Contact(
                name=current_contact_raw["name"],
                address=current_contact_raw["address"],
                phone=current_contact_raw["phone"],
                email=current_contact_raw["email"],
            ),
        )
    current_users = set()
    for current_user_raw in current_users_raw:
        if current_user_raw["id"] not in current_contacts:
            logger.error(
                'Contact information of user with id "%d" missing.',
                current_user_raw["id"],
            )
            return False
        current_users.add(
            db_util.User(
                name=current_user_raw["name"],
                email=current_user_raw["email"],
                api_key=current_user_raw["api_key"],
                role=current_user_raw["role"],
                contacts=frozenset(current_contacts[current_user_raw["id"]]),
            ),
        )
    expected_users = {_normalize_user(u) for u in db_util.USERS}
    delta_db = current_users - expected_users
    if delta_db:
        logger.error(
            "Additional data in database found: %s",
            delta_db,
        )
        return False
    delta_missing = expected_users - current_users
    if delta_missing:
        logger.error(
            "Missing data in database: %s",
            delta_missing,
        )
        return False
    logger.info("Database data integrity successfully verified.")
    return True
