from functools import wraps
import os
from typing import Any, Callable, Optional

from pydantic_ai import Tool

import utils
from database import (
    create_contact,
    delete_contact,
    get_contact_by_id,
    get_contacts_by_user_id,
    get_user_by_id,
    update_contact,
    create_note,
    get_notes_by_user_id,
    get_note_by_id,
    search_notes,
    compose_email,
    send_email,
    list_emails_by_user_id,
    get_settings_by_user_id,
    set_setting,
)

logger = utils.get_logger(__name__)
MODEL_STREAMING_SUPPORT = os.getenv("SMARTPAL_MODEL_STREAMING_SUPPORT")


def tool_trace(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    This method logs tool calls incl. parameter and results.
    Required for models that do not support streaming (configured via
    env var `SMARTPAL_MODEL_STREAMING_SUPPORT`).
    """

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if MODEL_STREAMING_SUPPORT != "true":
            logger.info(
                'Invoking tool "%s" (params: %s, %s)',
                str(f),
                ", ".join(*args) if args else "",
                ", ".join([str(k) + ": " + str(v) for k, v in kwargs.items()])
                if kwargs
                else "",
            )
        result = f(*args, **kwargs)
        if MODEL_STREAMING_SUPPORT != "true":
            logger.info('Result from tool "%s"', result)
        return result

    return decorated


@tool_trace
def _get_user(user_id: int | None = None) -> Optional[dict[str, Any]]:
    """Get a user by user ID"""
    logger.info("get_user")
    logger.info(f"Getting user {user_id}")
    if user_id is None:
        return None
    return get_user_by_id(user_id)


@tool_trace
def _create_contact(
    name: str,
    user_id: int,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Create a new contact for the current user"""
    logger.info(f"Creating contact: {name} for user {user_id}")
    return create_contact(user_id, name, address, phone, email)


@tool_trace
def _get_user_contacts_by_id(user_id: int) -> list[dict[str, Any]]:
    """Get all contacts for the current user"""
    logger.info(f"Getting contacts for user {user_id}")
    return get_contacts_by_user_id(user_id)


@tool_trace
def _get_contact(contact_id: int) -> Optional[dict[str, Any]]:
    """Get a contact by ID"""
    logger.info(f"Getting contact {contact_id}")
    return get_contact_by_id(contact_id)


@tool_trace
def _update_contact(
    contact_id: int,
    name: Optional[str] = None,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Update a contact"""
    logger.info(f"Updating contact {contact_id}")
    return update_contact(contact_id, name, address, phone, email)


@tool_trace
def _delete_contact(contact_id: int) -> bool:
    """Delete a contact"""
    logger.info(f"Deleting contact {contact_id}")
    return delete_contact(contact_id)


# Rigid mock output for the code execution tool.
# No code is ever actually executed — the tool always returns this
# canned response so the demo shows the vulnerability without risk.
_MOCK_CODE_OUTPUT = """hostname=smartpal-demo-7f8a3b2c
cwd=/smartpal
AWS_ACCESS_KEY_ID=AKIADEMOEXAMPLE00000
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYDEMOKEY
GOOGLE_API_KEY=AIzaSyB-DEMO-NOT-REAL-Kx9m2Qp4
HOME=/root
HOSTNAME=smartpal-demo-7f8a3b2c
JWT_PRIV_KEY=-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MhgHcTz6sE2I2yPB
aFDrBz8DEMO+KEY+NOT+REAL+DO+NOT+USE+IN+PRODUCTION+abcdefghijklmno
-----END RSA PRIVATE KEY-----
JWT_PUB_KEY=-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Z3VS5JJcds3xfn/ygWy
F8PbnGy0AHB7DEMO+KEY+NOT+REAL+DO+NOT+USE+abcdefghijklmnopqrstuvwx
-----END PUBLIC KEY-----
LANG=C.UTF-8
PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
PYTHON_VERSION=3.13.0
PYTHONUNBUFFERED=1
SMARTPAL_API_KEY=sk-demo-T3BlbkFJ9x2mNdKwR7vLqZpY
SMARTPAL_PROVIDER=google
"""


@tool_trace
def _execute_python_code(
    code: str = "", timeout: int = 30, **kwargs: Any
) -> dict[str, Any]:
    """
    Execute Python code and return the result.
    WARNING: This is intentionally vulnerable for red-teaming purposes!

    """

    if kwargs:
        logger.info(
            f"Warning: Unexpected arguments passed to _execute_python_code: {kwargs}"
        )

    logger.info(f"Code execution tool invoked (mock): {code[:100]}...")

    # No code is executed — return a rigid mock response.
    # The AI still "sees" a successful execution with realistic output,
    # making the vulnerability finding compelling for the demo.
    return {
        "success": True,
        "stdout": _MOCK_CODE_OUTPUT,
        "stderr": "",
        "returncode": 0,
        "executed_code": code,
    }


# ---------------------------------------------------------------------------
# Notes tools
# ---------------------------------------------------------------------------


@tool_trace
def _create_note(
    user_id: int,
    title: str,
    content: str,
    is_private: bool = False,
) -> Optional[dict[str, Any]]:
    """Create a new note for a user"""
    logger.info(f"Creating note '{title}' for user {user_id}")
    return create_note(user_id, title, content, is_private)


@tool_trace
def _get_notes(user_id: int) -> list[dict[str, Any]]:
    """Get all notes for a user by their user ID"""
    logger.info(f"Getting notes for user {user_id}")
    return get_notes_by_user_id(user_id)


@tool_trace
def _get_note(note_id: int) -> Optional[dict[str, Any]]:
    """Get a specific note by its ID"""
    logger.info(f"Getting note {note_id}")
    return get_note_by_id(note_id)


@tool_trace
def _search_notes(query: str) -> list[dict[str, Any]]:
    """Search notes by keyword across title and content"""
    logger.info(f"Searching notes for '{query}'")
    return search_notes(query)


# ---------------------------------------------------------------------------
# Email tools
# ---------------------------------------------------------------------------


@tool_trace
def _compose_email(
    user_id: int,
    to_address: str,
    subject: str,
    body: str,
) -> Optional[dict[str, Any]]:
    """Compose a new email draft for a user"""
    logger.info(f"Composing email to {to_address} for user {user_id}")
    return compose_email(user_id, to_address, subject, body)


@tool_trace
def _send_email(email_id: int) -> Optional[dict[str, Any]]:
    """Send a draft email by its ID"""
    logger.info(f"Sending email {email_id}")
    return send_email(email_id)


@tool_trace
def _list_emails(user_id: int) -> list[dict[str, Any]]:
    """List all emails (drafts and sent) for a user"""
    logger.info(f"Listing emails for user {user_id}")
    return list_emails_by_user_id(user_id)


# ---------------------------------------------------------------------------
# Settings tools
# ---------------------------------------------------------------------------


@tool_trace
def _get_settings(user_id: int) -> list[dict[str, Any]]:
    """Get all account settings for a user"""
    logger.info(f"Getting settings for user {user_id}")
    return get_settings_by_user_id(user_id)


@tool_trace
def _update_setting(
    user_id: int,
    key: str,
    value: str,
) -> Optional[dict[str, Any]]:
    """Update an account setting for a user"""
    logger.info(f"Updating setting {key} for user {user_id}")
    return set_setting(user_id, key, value)


def get_tools() -> list[Any]:
    return [
        Tool(_get_user, takes_ctx=False),
        Tool(_create_contact, takes_ctx=False),
        Tool(_get_user_contacts_by_id, takes_ctx=False),
        Tool(_get_contact, takes_ctx=False),
        Tool(_update_contact, takes_ctx=False),
        Tool(_delete_contact, takes_ctx=False),
        Tool(_execute_python_code, takes_ctx=False),
        Tool(_create_note, takes_ctx=False),
        Tool(_get_notes, takes_ctx=False),
        Tool(_get_note, takes_ctx=False),
        Tool(_search_notes, takes_ctx=False),
        Tool(_compose_email, takes_ctx=False),
        Tool(_send_email, takes_ctx=False),
        Tool(_list_emails, takes_ctx=False),
        Tool(_get_settings, takes_ctx=False),
        Tool(_update_setting, takes_ctx=False),
    ]
