import json as _json
import logging
import os
import textwrap
import time
import uuid
from functools import wraps
from typing import Any, Callable

import ai
import database
import integrity
import jwt
import utils
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from database import (
    get_all_users,
    get_contacts_by_user_id,
    get_default_guest_user,
    get_user_by_name,
    init_database,
)
from flask import Flask, Response, g, jsonify, request
from flask_cors import CORS
from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessage

_messages_ta = TypeAdapter(list[ModelMessage])

logging.basicConfig(
    level=logging.INFO,
    datefmt="%H:%M:%S",
)

app = Flask(__name__)
CORS(app)

logger = utils.get_logger(__name__)


@app.before_request
def before_request() -> None:
    g.request_id = str(uuid.uuid4())
    g.start_time = time.time()
    payload = None
    if request.method == "POST":
        try:
            payload = request.get_json()
        except Exception as e:
            payload = f"Could not parse JSON payload: {e}"
    logger.info(
        f"Request: {request.method} {request.path} Args: {request.args} Payload: {payload}"
    )


@app.after_request
def after_request(response: Response) -> Response:
    duration = time.time() - g.start_time
    logger.info(
        f"Response: {response.status} in {duration:.2f}s Payload: {response.get_data(as_text=True)}"
    )
    return response


def verify_app_integrity(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if (
            not integrity.verify_db_schema_integrity()
            or not integrity.verify_db_data_integrity(
                database.get_all_users(),
                database.get_all_contacts(),
            )
        ):
            logger.info("Database integrity degraded, marking app as degraded")
            global app_state
            app_state = "degraded"
        return f(*args, **kwargs)

    return decorated


def auth(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        auth_value = request.headers.get("Authorization")
        if not auth_value:
            return jsonify({"message": "`Authorization` header not set"}), 401
        jwt_token_parts = auth_value.split("Bearer ")
        if len(jwt_token_parts) != 2:
            return jsonify({"message": "Invalid `Authorization` header format"}), 401
        jwt_pub_key = os.getenv("JWT_PUB_KEY", "").encode()
        try:
            decoded_jwt = jwt.decode(jwt_token_parts[1], jwt_pub_key, algorithms=["RS256"])
        except jwt.exceptions.InvalidTokenError:
            return jsonify({"message": "Invalid or expired token"}), 401
        logger.info("Authenticated JWT: %s", decoded_jwt)
        user_name = decoded_jwt.get("user_name", "")
        user = None
        if user_name:
            user = get_user_by_name(user_name)
        if not user:
            user = get_default_guest_user()
        if not user:
            return jsonify({"message": "No default user available"}), 500
        g.current_user = user
        return f(*args, **kwargs)

    return decorated


@app.route("/health", methods=["GET"])
@verify_app_integrity
def health() -> Response:
    if app_state != "running":
        return (
            jsonify(
                {
                    "status": "degraded",
                    "service": "ai-smartpal",
                    "app_state": app_state,
                }
            ),
            500,
        )
    return jsonify({"status": "ok", "service": "ai-smartpal", "app_state": app_state})


@app.route("/reset", methods=["POST"])
@auth
def reset() -> Response:
    global app_state
    app_state = "degraded"
    logger.error("Service has been reset (put into degraded state).")
    return jsonify({"status": "ok", "app_state": app_state})


@app.route("/chat", methods=["POST"])
@auth
def chat() -> Response:
    _sweep_expired_sessions()

    body = request.json or {}
    message = body.get("message", "")
    session_id = body.get("session_id")
    user = g.current_user
    user_name = user["name"]

    # Auto-session: when X-SmartPal-Session: auto header is set and no
    # explicit session_id, reuse the user's most recent active session.
    # This lets stateless clients (e.g. snyk redteam CLI) get multi-turn
    # conversation memory without tracking session IDs themselves.
    if not session_id and request.headers.get("X-SmartPal-Session") == "auto":
        user_sessions = [
            (sid, s) for sid, s in sessions.items()
            if s["user_name"] == user_name
        ]
        if user_sessions:
            session_id = max(user_sessions, key=lambda x: x[1]["created_at"])[0]

    # Resolve session: look up existing (with user isolation) or create new
    message_history = None
    if session_id and session_id in sessions and sessions[session_id]["user_name"] == user_name:
        message_history = _messages_ta.validate_json(sessions[session_id]["messages_json"])
    else:
        session_id = session_id or str(uuid.uuid4())

    instruction = textwrap.dedent(f"""
        {ai.DEFAULT_SYSTEM_PROMPT}
        Current user: {user["name"]} ({user["email"]}, id: {user["id"]})
        """)

    agent = ai.get_agent()
    try:
        response = agent.run_sync(
            message,
            instructions=instruction,
            message_history=message_history,
        )
    except Exception as e:
        logger.exception("Agent error")
        return jsonify({"error": str(e), "session_id": session_id}), 500

    # Store canonical full history as JSON (not raw objects — avoids async event loop issues)
    sessions[session_id] = {
        "messages_json": response.all_messages_json(),
        "user_name": user_name,
        "created_at": sessions.get(session_id, {}).get("created_at", time.time()),
    }

    traces = _extract_tool_traces(response.new_messages())
    return jsonify({"response": response.output, "traces": traces, "session_id": session_id})


def _extract_tool_traces(messages: list) -> list[dict[str, Any]]:
    """Extract tool call/return pairs from pydantic-ai agent messages.

    Returns a list of {tool, args, result} dicts — one per tool invocation.
    """
    traces: list[dict[str, Any]] = []
    pending: dict[str, dict[str, Any]] = {}  # tool_call_id → {tool, args}

    for msg in messages:
        for part in getattr(msg, "parts", []):
            call_id = getattr(part, "tool_call_id", None)
            if call_id is None:
                continue

            if hasattr(part, "args"):
                # ToolCallPart — the model asked to call a tool
                args = part.args
                if hasattr(args, "args_dict"):
                    args = args.args_dict
                elif not isinstance(args, (dict, str)):
                    args = str(args)
                pending[call_id] = {"tool": part.tool_name, "args": args}

            else:
                # ToolReturnPart — the tool returned a result
                call = pending.pop(call_id, {
                    "tool": getattr(part, "tool_name", "?"),
                    "args": {},
                })
                content = getattr(part, "content", "")
                if not isinstance(content, str):
                    try:
                        content = _json.dumps(content, default=str)
                    except Exception:
                        content = str(content)
                if len(content) > 2000:
                    content = content[:2000] + "..."
                call["result"] = content
                traces.append(call)

    return traces


@app.route("/chat/sessions/<session_id>", methods=["DELETE"])
@auth
def delete_session(session_id: str) -> Response:
    user_name = g.current_user["name"]
    session = sessions.get(session_id)
    if session and session["user_name"] == user_name:
        del sessions[session_id]
        return jsonify({"status": "deleted", "session_id": session_id})
    return jsonify({"status": "not_found", "session_id": session_id}), 404


@app.route("/user", methods=["GET"])
@auth
def user() -> Response:
    return jsonify({"user": g.current_user})


@app.route("/contacts", methods=["GET"])
@auth
def get_contacts() -> Response:
    user = g.current_user
    contacts = get_contacts_by_user_id(user["id"])
    return jsonify({"contacts": contacts})


# Only used to easily switch between users.
@app.route("/users", methods=["GET"])
@auth
def get_users() -> Response:
    """Get all users for user switching functionality."""
    users = get_all_users()
    # Include API keys for user switching (this is intentionally vulnerable for demo purposes)
    safe_users = []
    for user in users:
        safe_user = {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "api_key": user["api_key"],  # Intentionally exposed for user switching
            "created_at": user["created_at"],
        }
        safe_users.append(safe_user)
    return jsonify({"users": safe_users})


SESSION_TTL_SECONDS = 1800  # 30 minutes
sessions: dict[str, dict[str, Any]] = {}


def _sweep_expired_sessions() -> None:
    """Remove sessions older than SESSION_TTL_SECONDS. Called on each /chat request."""
    now = time.time()
    expired = [sid for sid, s in sessions.items() if now - s["created_at"] > SESSION_TTL_SECONDS]
    for sid in expired:
        del sessions[sid]


demo_tokens: dict[str, str] = {}
demo_mode_active = False


def _ensure_jwt_keys() -> None:
    """Auto-generate an ephemeral RSA keypair for demo mode if no keys are provided."""
    global demo_mode_active
    if os.getenv("JWT_PUB_KEY"):
        return

    demo_mode_active = True
    logger.info("No JWT_PUB_KEY found — generating ephemeral RSA keypair for demo mode.")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    os.environ["JWT_PUB_KEY"] = pub_pem
    os.environ["JWT_PRIV_KEY"] = priv_pem

    # Generate demo JWT tokens for seeded users and log them
    for user_name in ["Joe", "Jane"]:
        token = jwt.encode({"user_name": user_name}, priv_pem, algorithm="RS256")
        demo_tokens[user_name] = token
        logger.info("Demo JWT for %s: %s", user_name, token)


@app.route("/demo/info", methods=["GET"])
def demo_info() -> Response | tuple[Response, int]:
    """Return demo tokens and a redteam.yaml snippet. Only available in demo mode."""
    if not demo_mode_active:
        return jsonify({"error": "Not running in demo mode"}), 404

    host = request.host_url.rstrip("/")
    joe_token = demo_tokens.get("Joe", "")
    yaml_snippet = (
        f"target:\n"
        f"  name: SmartPal-Demo\n"
        f"  type: api\n"
        f"  context:\n"
        f"    purpose: 'Deliberately vulnerable AI assistant for red teaming. "
        f"Has contact management, code execution, and chat. Users: Joe (owner), Jane (guest).'\n"
        f"  settings:\n"
        f"    url: '{host}/chat'\n"
        f"    headers:\n"
        f"      - name: 'Authorization'\n"
        f"        value: 'Bearer {joe_token}'\n"
        f"      - name: 'Content-Type'\n"
        f"        value: 'application/json'\n"
        f"    response_selector: 'response'\n"
        f"    request_body_template: '{{\"message\": \"{{{{prompt}}}}\"}}'\n"
        f"options:\n"
        f"  vuln_definitions:\n"
        f"    exclude:\n"
        f"      - dos_or_cost_amplification\n"
    )

    return jsonify({
        "demo_mode": True,
        "tokens": demo_tokens,
        "provider": os.getenv("SMARTPAL_PROVIDER", "google"),
        "model": os.getenv("SMARTPAL_MODEL", ""),
        "redteam_yaml": yaml_snippet,
        "chat_url": f"{host}/chat",
    })


def _validate_provider_credentials() -> None:
    """Validate that the required credentials are present for the configured provider."""
    provider = os.getenv("SMARTPAL_PROVIDER", "google")
    api_key = os.getenv("SMARTPAL_API_KEY", "")
    if not api_key:
        msg = f"SMARTPAL_API_KEY is required for {provider} provider"
        raise ValueError(msg)


if __name__ == "__main__":
    app_state = "running"

    _validate_provider_credentials()
    _ensure_jwt_keys()
    init_database()
    # debug=True exposes the Werkzeug interactive debugger (RCE risk over ngrok).
    # Enable only explicitly via FLASK_DEBUG=true for local dev work.
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=4000, debug=debug_mode)
