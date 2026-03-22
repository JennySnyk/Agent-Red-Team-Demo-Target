import sqlite3

from typing import Any
from pathlib import Path

import db_util
import integrity

import utils

logger = utils.get_logger(__name__)


def init_database() -> None:
    """Initialize the database with the users table and seed data."""
    if integrity.verify_db_schema_integrity() and integrity.verify_db_data_integrity(
        get_all_users(),
        get_all_contacts(),
    ):
        return
    logger.info("Database integrity degraded, deleting it...")
    Path(db_util.DATABASE_PATH).unlink()

    conn = db_util.get_db_connection()
    logger.info("Initializing database...")
    try:
        for sql_stmt in db_util.DATABASE_SCHEMA:
            conn.execute(sql_stmt)
        conn.commit()

        for user in db_util.USERS:
            user_raw = create_user(
                name=user.name,
                email=user.email,
                api_key=user.api_key,
                role=user.role,
            )
            if not user_raw:
                logger.error('Failed to create user "%s"', user.name)
                msg = f'Failed to create user "{user.name}"'
                raise RuntimeError(msg)

            for contact in user.contacts:
                contact_raw = create_contact(
                    user_id=user_raw["id"],
                    name=contact.name,
                    address=contact.address,
                    phone=contact.phone,
                    email=contact.email,
                )
                if not contact_raw:
                    logger.error('Failed to create contact "%s"', contact.name)
                    msg = f'Failed to create contact "{contact.name}"'
                    raise RuntimeError(msg)

            for note in user.notes:
                note_raw = create_note(
                    user_id=user_raw["id"],
                    title=note.title,
                    content=note.content,
                    is_private=note.is_private,
                )
                if not note_raw:
                    logger.error('Failed to create note "%s"', note.title)
                    msg = f'Failed to create note "{note.title}"'
                    raise RuntimeError(msg)

            for email in user.emails:
                email_raw = compose_email(
                    user_id=user_raw["id"],
                    to_address=email.to_address,
                    subject=email.subject,
                    body=email.body,
                )
                if not email_raw:
                    logger.error('Failed to create email "%s"', email.subject)
                    msg = f'Failed to create email "{email.subject}"'
                    raise RuntimeError(msg)
                if email.status == "sent":
                    send_email(email_raw["id"])

            for setting in user.settings:
                set_setting(
                    user_id=user_raw["id"],
                    key=setting.key,
                    value=setting.value,
                )
    except Exception as e:
        logger.error("Error initializing database: %s", e)
        conn.rollback()
        raise
    finally:
        conn.close()
    logger.info("Database initialized.")


def create_user(
    *,
    name: str,
    email: str,
    role: str = "guest",
    api_key: str | None = None,
) -> dict[str, Any] | None:
    """Create a new user with the specified role."""
    conn = db_util.get_db_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO users (name, email, api_key, role)
            VALUES (?, ?, ?, ?)
        """,
            (name, email, api_key, role),
        )

        user_id = cursor.lastrowid
        conn.commit()

        if user_id is None:
            return None

        return get_user_by_id(user_id)

    except sqlite3.IntegrityError as e:
        logger.error("Error creating user: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected error creating user: %s", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def get_user_by_api_key(api_key: str) -> dict[str, Any] | None:
    """Get user by API key."""
    conn = db_util.get_db_connection()
    try:
        user = conn.execute(
            """
            SELECT id, name, email, api_key, role, created_at
            FROM users
            WHERE api_key = ?
        """,
            (api_key,),
        ).fetchone()

        return dict(user) if user else None
    finally:
        conn.close()


def get_user_by_name(name: str) -> dict[str, Any] | None:
    """Get user by name."""
    conn = db_util.get_db_connection()
    try:
        user = conn.execute(
            """
            SELECT id, name, email, api_key, role, created_at
            FROM users
            WHERE name = ?
        """,
            (name,),
        ).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """Get user by ID."""
    conn = db_util.get_db_connection()
    try:
        user = conn.execute(
            "SELECT id, name, email, api_key, role, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(user) if user else None
    except Exception as e:
        logger.error("Error getting user: %s", e)
        return None
    finally:
        conn.close()


def get_default_guest_user() -> dict[str, Any] | None:
    """Get the default guest user."""
    conn = db_util.get_db_connection()
    try:
        # Get the first guest user (the default one)
        user = conn.execute("""
            SELECT id, name, email, api_key, role, created_at
            FROM users
            WHERE role = 'guest'
            ORDER BY created_at ASC
            LIMIT 1
        """).fetchone()

        return dict(user) if user else None
    finally:
        conn.close()


def get_all_users() -> list[dict[str, Any]]:
    """Get all users."""
    conn = db_util.get_db_connection()
    try:
        users = conn.execute("""
            SELECT id, name, email, api_key, role, created_at
            FROM users
            ORDER BY created_at ASC
        """).fetchall()

        return [dict(user) for user in users]
    finally:
        conn.close()


# Contact management functions


def create_contact(
    user_id: int,
    name: str,
    address: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> dict[str, Any] | None:
    """Create a new contact for a user."""
    conn = db_util.get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO contacts (user_id, name, address, phone, email)
            VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, name, address, phone, email),
        )

        contact_id = cursor.lastrowid
        conn.commit()

        if contact_id is None:
            return None

        return get_contact_by_id(contact_id)

    except Exception as e:
        logger.error("Error creating contact: %s", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def get_contact_by_id(contact_id: int) -> dict[str, Any] | None:
    """Get a contact by ID."""
    conn = db_util.get_db_connection()
    try:
        contact = conn.execute(
            """
            SELECT id, user_id, name, address, phone, email, created_at,
            updated_at
            FROM contacts
            WHERE id = ?
        """,
            (contact_id,),
        ).fetchone()

        return dict(contact) if contact else None
    finally:
        conn.close()


def get_contacts_by_user_id(user_id: int) -> list[dict[str, Any]]:
    """Get all contacts for a user."""
    conn = db_util.get_db_connection()
    current_user = get_user_by_id(user_id)
    _user_id: str | int = user_id
    if current_user and current_user["role"] == "owner":
        _user_id = "%"
        logger.info("Selecting all contacts")
    try:
        contacts = conn.execute(
            """
            SELECT id, user_id, name, address, phone, email, created_at,
            updated_at
            FROM contacts
            WHERE user_id LIKE ?
            ORDER BY name ASC
        """,
            (_user_id,),
        ).fetchall()

        return [dict(contact) for contact in contacts]
    finally:
        conn.close()


def get_all_contacts() -> list[dict[str, Any]]:
    """Get all contacts (for admin purposes)."""
    conn = db_util.get_db_connection()
    try:
        contacts = conn.execute("""
            SELECT id, user_id, name, address, phone, email, created_at,
            updated_at
            FROM contacts
            ORDER BY name ASC
        """).fetchall()

        return [dict(contact) for contact in contacts]
    finally:
        conn.close()


def update_contact(
    contact_id: int,
    name: str | None = None,
    address: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> dict[str, Any] | None:
    """Update a contact."""
    conn = db_util.get_db_connection()
    try:
        # Build dynamic update query based on provided fields
        updates = []
        params: list[Any] = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if address is not None:
            updates.append("address = ?")
            params.append(address)
        if phone is not None:
            updates.append("phone = ?")
            params.append(phone)
        if email is not None:
            updates.append("email = ?")
            params.append(email)

        if not updates:
            return get_contact_by_id(contact_id)

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(contact_id)

        query = f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?"
        conn.execute(query, params)
        conn.commit()

        return get_contact_by_id(contact_id)

    except Exception as e:
        logger.error("Error updating contact: %s", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def delete_contact(contact_id: int) -> bool:
    """Delete a contact."""
    conn = db_util.get_db_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM contacts WHERE id = ?",
            (contact_id,),
        )
        conn.commit()
        return bool(cursor.rowcount > 0)
    except Exception as e:
        logger.error("Error deleting contact: %s", e)
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


def create_note(
    user_id: int,
    title: str,
    content: str,
    is_private: bool = False,
) -> dict[str, Any] | None:
    """Create a new note for a user."""
    conn = db_util.get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO notes (user_id, title, content, is_private)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, title, content, int(is_private)),
        )
        note_id = cursor.lastrowid
        conn.commit()
        if note_id is None:
            return None
        return get_note_by_id(note_id)
    except Exception as e:
        logger.error("Error creating note: %s", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def get_note_by_id(note_id: int) -> dict[str, Any] | None:
    """Get a note by ID."""
    conn = db_util.get_db_connection()
    try:
        note = conn.execute(
            "SELECT id, user_id, title, content, is_private, created_at, updated_at FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        return dict(note) if note else None
    finally:
        conn.close()


def get_notes_by_user_id(user_id: int) -> list[dict[str, Any]]:
    """Get all notes for a user."""
    conn = db_util.get_db_connection()
    try:
        notes = conn.execute(
            """
            SELECT id, user_id, title, content, is_private, created_at, updated_at
            FROM notes
            WHERE user_id = ?
            ORDER BY created_at DESC
        """,
            (user_id,),
        ).fetchall()
        return [dict(n) for n in notes]
    finally:
        conn.close()


def search_notes(query: str) -> list[dict[str, Any]]:
    """Search notes by title or content across all users."""
    conn = db_util.get_db_connection()
    try:
        notes = conn.execute(
            """
            SELECT id, user_id, title, content, is_private, created_at, updated_at
            FROM notes
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY created_at DESC
        """,
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
        return [dict(n) for n in notes]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------


def compose_email(
    user_id: int,
    to_address: str,
    subject: str,
    body: str,
) -> dict[str, Any] | None:
    """Compose a new email draft."""
    conn = db_util.get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO emails (user_id, to_address, subject, body, status)
            VALUES (?, ?, ?, ?, 'draft')
        """,
            (user_id, to_address, subject, body),
        )
        email_id = cursor.lastrowid
        conn.commit()
        if email_id is None:
            return None
        return get_email_by_id(email_id)
    except Exception as e:
        logger.error("Error composing email: %s", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def send_email(email_id: int) -> dict[str, Any] | None:
    """Mark an email as sent."""
    conn = db_util.get_db_connection()
    try:
        conn.execute(
            "UPDATE emails SET status = 'sent' WHERE id = ? AND status = 'draft'",
            (email_id,),
        )
        conn.commit()
        return get_email_by_id(email_id)
    except Exception as e:
        logger.error("Error sending email: %s", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def get_email_by_id(email_id: int) -> dict[str, Any] | None:
    """Get an email by ID."""
    conn = db_util.get_db_connection()
    try:
        email = conn.execute(
            "SELECT id, user_id, to_address, subject, body, status, created_at FROM emails WHERE id = ?",
            (email_id,),
        ).fetchone()
        return dict(email) if email else None
    finally:
        conn.close()


def list_emails_by_user_id(user_id: int) -> list[dict[str, Any]]:
    """List all emails for a user."""
    conn = db_util.get_db_connection()
    try:
        emails = conn.execute(
            """
            SELECT id, user_id, to_address, subject, body, status, created_at
            FROM emails
            WHERE user_id = ?
            ORDER BY created_at DESC
        """,
            (user_id,),
        ).fetchall()
        return [dict(e) for e in emails]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def get_settings_by_user_id(user_id: int) -> list[dict[str, Any]]:
    """Get all settings for a user."""
    conn = db_util.get_db_connection()
    try:
        settings = conn.execute(
            "SELECT id, user_id, key, value FROM settings WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return [dict(s) for s in settings]
    finally:
        conn.close()


def set_setting(
    user_id: int,
    key: str,
    value: str,
) -> dict[str, Any] | None:
    """Create or update a setting for a user."""
    conn = db_util.get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO settings (user_id, key, value)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
        """,
            (user_id, key, value),
        )
        conn.commit()
        setting = conn.execute(
            "SELECT id, user_id, key, value FROM settings WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        return dict(setting) if setting else None
    except Exception as e:
        logger.error("Error setting %s: %s", key, e)
        conn.rollback()
        return None
    finally:
        conn.close()
