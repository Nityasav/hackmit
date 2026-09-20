"""Laptop-only access boundary with optional password sessions and workspace ACLs.

Not an internet deployment/authentication service. Configure SCHOOLTRACE_USERS as
JSON {username: {password_hash: salt_hex: scrypt_hex (without spaces), role,
workspaces: [workspace IDs]}}. Admins can access all workspaces. Never store a key
or password in frontend code. Sessions are process-local and expire after 8h.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/access", tags=["Laptop access"])
SESSIONS = {}
ATTEMPTS = {}
ORIGINS = {"http://localhost:3000", "http://127.0.0.1:3000"} | {
    origin.strip() for origin in os.getenv("SCHOOLTRACE_ALLOWED_ORIGINS", "").split(",") if origin.strip()
}
# Vercel gives every deployment its own hostname, so previews need a pattern rather than a list.
def _origin_pattern():
    raw = os.getenv("SCHOOLTRACE_ALLOWED_ORIGIN_REGEX")
    if not raw:
        return None
    try:
        return re.compile(raw)
    except re.error as exc:
        # Refusing to start is right — an unparseable allowlist must not quietly allow nothing or
        # everything — but the bare re.error in a host's log says nothing about which value is wrong.
        raise RuntimeError(f"SCHOOLTRACE_ALLOWED_ORIGIN_REGEX is not a valid regular expression ({exc}). "
                           f"Value received: {raw!r}") from None


ORIGIN_PATTERN = _origin_pattern()
# Hosting is opt-in per hostname. Without this the API answers loopback only, which is the single
# thing standing between an unconfigured deployment and an open admin API: identity() hands anyone
# admin over every workspace when SCHOOLTRACE_USERS is unset.
PUBLIC_HOSTS = {host.strip().lower() for host in os.getenv("SCHOOLTRACE_PUBLIC_HOSTS", "").split(",") if host.strip()}


def users():
    raw = os.getenv("SCHOOLTRACE_USERS")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or not value:
            raise ValueError()
        for user in value.values():
            if user.get("role") not in {"admin", "reviewer", "analyst", "viewer"} or not isinstance(user.get("workspaces", []), list):
                raise ValueError()
            salt, digest = user["password_hash"].split(":")
            if len(bytes.fromhex(salt)) < 16 or len(bytes.fromhex(digest)) != 64:
                raise ValueError()
        return value
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(503, "Access configuration is invalid; refusing access.") from None


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ":" + digest.hex()


def identity(request):
    configured = users()
    if not configured:
        return {"name": "local-reviewer", "role": "admin", "workspaces": ["*"], "mode": "local_admin"}
    session = SESSIONS.get(hashlib.sha256(request.cookies.get("schooltrace_session", "").encode()).hexdigest())
    if not session or session[1] < time.time() or session[0] not in configured:
        raise HTTPException(401, "Sign in to access this workspace.")
    user = configured[session[0]]
    return {"name": session[0], "role": user["role"], "workspaces": user.get("workspaces", []), "mode": "authenticated"}


def authorize_workspace(user, ws):
    if user["role"] != "admin" and ws not in user["workspaces"]:
        raise HTTPException(403, "This account cannot access that workspace.")


async def guard(request):
    # Liveness is checked before the host gate. A platform's health probe arrives on an internal
    # hostname that is not in SCHOOLTRACE_PUBLIC_HOSTS, so guarding it would 403 every probe, leave
    # the deployment permanently unhealthy, and surface as a 502 from the edge. The endpoint
    # returns a fixed string and reads nothing.
    if request.url.path == "/api/health":
        return
    host = request.url.hostname
    peer = request.client.host if request.client else ""
    testing = host == "testserver" and peer == "testclient"
    hosted = bool(PUBLIC_HOSTS) and (host or "").lower() in PUBLIC_HOSTS
    if hosted and not users():
        # Fails closed rather than serving: opening the gate without accounts would publish an
        # API on which every caller is an admin.
        raise HTTPException(503, "Public hosting requires SCHOOLTRACE_USERS; refusing to serve an unauthenticated admin API.")
    if not testing and not hosted and (host not in {"localhost", "127.0.0.1", "::1"} or peer not in {"127.0.0.1", "::1"}):
        raise HTTPException(403, "This server accepts loopback connections only; set SCHOOLTRACE_PUBLIC_HOSTS to host it.")
    origin = request.headers.get("origin")
    if origin and origin not in ORIGINS and not (ORIGIN_PATTERN and ORIGIN_PATTERN.fullmatch(origin)):
        raise HTTPException(403, "Untrusted browser origin.")
    if request.method == "OPTIONS" or request.url.path in {"/api/health", "/api/access/login", "/api/access/status"}:
        return
    if not request.url.path.startswith("/api") and not users():
        return
    user = identity(request)
    request.state.user = user
    if request.url.path == "/api/access/logout":
        return
    write = request.method not in {"GET", "HEAD", "OPTIONS"}
    if write and user["role"] == "viewer":
        raise HTTPException(403, "This account is read-only.")
    path = request.url.path
    if write and path == "/api/workspaces" and user["role"] != "admin":
        raise HTTPException(403, "Only admins can create workspaces.")
    match = re.search(r"/workspaces/([^/]+)", path)
    if match:
        authorize_workspace(user, match[1])
    if path.startswith("/api/cfo/runs/"):
        from .cfo.api import runtime
        try:
            run = runtime(request).repository.get(path.split("/")[4])
        except KeyError:
            raise HTTPException(404, "Run not found.")
        authorize_workspace(user, run.request.workspace)
    if write and (path == "/api/cfo/runs" or path.startswith("/api/approvals/")):
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 65536:
                raise HTTPException(413, "Run/decision request exceeds 64 KB.")
        request._body = bytes(content)
        try:
            body = json.loads(content)
            if not isinstance(body, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise HTTPException(400, "Expected a JSON request object.") from None
        workspace = body.get("workspace")
        if not isinstance(workspace, str) or not workspace:
            raise HTTPException(422, "A workspace is required.")
        authorize_workspace(user, workspace)
        if path.startswith("/api/approvals/") and user["role"] not in {"admin", "reviewer"}:
            raise HTTPException(403, "Reviewer role required.")


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


@router.get("/status")
def status(request: Request):
    configured = bool(users())
    try:
        user = identity(request)
    except HTTPException:
        user = None
    return {"authentication_configured": configured, "user": user, "local_only": True,
            "retention": "Records stay on this laptop until an admin deletes the workspace. Backups and filesystem remnants are not erased by logical deletion.",
            "sensitive_data_ready": False}


@router.post("/login")
def login(body: Login, response: Response):
    now = time.time()
    recent = [t for t in ATTEMPTS.get("local", []) if now - t < 300]
    if len(recent) >= 10:
        raise HTTPException(429, "Too many attempts. Wait five minutes.")
    ATTEMPTS["local"] = recent + [now]
    user = users().get(body.username)
    encoded = user["password_hash"] if user else "00" * 16 + ":" + "00" * 64
    salt, digest = encoded.split(":")
    actual = hashlib.scrypt(body.password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    if not user or not hmac.compare_digest(actual, digest):
        raise HTTPException(401, "Invalid credentials.")
    for key, value in list(SESSIONS.items()):
        if value[1] < now:
            SESSIONS.pop(key, None)
    token = secrets.token_urlsafe(32)
    SESSIONS[hashlib.sha256(token.encode()).hexdigest()] = (body.username, now + 8 * 3600)
    # HTTP is loopback-only. Use TLS + Secure cookies before any hosted deployment.
    # Hosted, the web app and the API are different sites, and a strict cookie is never sent
    # across them — sign-in would appear to succeed and every later call would be anonymous.
    # SameSite=None requires Secure, so this only holds over TLS, which a host terminates for us.
    cross_site = bool(PUBLIC_HOSTS)
    response.set_cookie("schooltrace_session", token, httponly=True,
                        samesite="none" if cross_site else "strict", secure=cross_site,
                        max_age=8 * 3600)
    return {"name": body.username, "role": user["role"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    SESSIONS.pop(hashlib.sha256(request.cookies.get("schooltrace_session", "").encode()).hexdigest(), None)
    response.delete_cookie("schooltrace_session")
    return {"signed_out": True}
