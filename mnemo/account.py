"""Mnemo accounts (Firebase Authentication).

Email sign-up/sign-in use Firebase's REST API directly. Google sign-in opens the
Mnemo website in your normal browser; after you sign in there, the page sends the
Firebase tokens back to this computer (127.0.0.1) with a one-time `state` code.

The Firebase web config is read from website/public/firebase-config.js, so you
only fill it in once for both the website and the app.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

import httpx

from .config import HOME

ACCOUNT = HOME / "account.json"
SITE_CONFIG = Path(__file__).resolve().parent.parent / "website" / "public" / "firebase-config.js"
IDT = "https://identitytoolkit.googleapis.com/v1/accounts:"
_pending_states: dict[str, float] = {}


class AuthError(Exception):
    pass


FRIENDLY = {
    "EMAIL_EXISTS": "An account with this email already exists. Sign in instead.",
    "EMAIL_NOT_FOUND": "No account with that email. Create one first.",
    "INVALID_PASSWORD": "Wrong password.", "INVALID_LOGIN_CREDENTIALS": "Wrong email or password.",
    "INVALID_EMAIL": "That email address doesn't look right.",
    "WEAK_PASSWORD": "Use a password with at least 6 characters.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Wait a minute and try again.",
    "USER_DISABLED": "This account has been disabled.",
    "OPERATION_NOT_ALLOWED": "Email sign-in isn't enabled in the Firebase console yet.",
}


def firebase_config() -> dict:
    try:
        text = SITE_CONFIG.read_text()
    except FileNotFoundError:
        return {}
    return dict(re.findall(r'(\w+):\s*"([^"]*)"', text))


def configured() -> bool:
    c = firebase_config()
    return bool(c.get("apiKey") and c.get("authDomain"))


def _key() -> str:
    k = firebase_config().get("apiKey")
    if not k:
        raise AuthError("Accounts aren't set up yet: add your Firebase config to website/public/firebase-config.js.")
    return k


def _post(url: str, body: dict) -> dict:
    r = httpx.post(url, params={"key": _key()}, json=body, timeout=15)
    data = r.json()
    if r.status_code != 200:
        code = data.get("error", {}).get("message", "UNKNOWN").split(" ")[0]
        raise AuthError(FRIENDLY.get(code, code.replace("_", " ").capitalize()))
    return data


def _save(data: dict, name: str = "") -> dict:
    acc = {"uid": data["localId"], "email": data.get("email", ""), "name": name or data.get("displayName", ""),
           "photo": data.get("photoUrl", ""), "id_token": data["idToken"], "refresh_token": data["refreshToken"],
           "expires": time.time() + int(data.get("expiresIn", 3600)) - 60, "signed_in": time.time()}
    HOME.mkdir(parents=True, exist_ok=True)
    ACCOUNT.write_text(json.dumps(acc))
    ACCOUNT.chmod(0o600)
    return public(acc)


def public(acc: dict | None) -> dict:
    if not acc:
        return {"signed_in": False, "configured": configured()}
    return {"signed_in": True, "configured": True, **{k: acc.get(k, "") for k in ("uid", "email", "name", "photo")}}


def current() -> dict | None:
    try:
        return json.loads(ACCOUNT.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def sign_up(email: str, password: str, name: str = "") -> dict:
    data = _post(IDT + "signUp", {"email": email, "password": password, "returnSecureToken": True})
    if name:
        try:
            _post(IDT + "update", {"idToken": data["idToken"], "displayName": name, "returnSecureToken": False})
        except AuthError:
            pass
    try:  # verification email; signing in doesn't wait for it
        _post(IDT + "sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": data["idToken"]})
    except AuthError:
        pass
    return _save(data, name)


def sign_in(email: str, password: str) -> dict:
    return _save(_post(IDT + "signInWithPassword", {"email": email, "password": password, "returnSecureToken": True}))


def reset_password(email: str):
    _post(IDT + "sendOobCode", {"requestType": "PASSWORD_RESET", "email": email})


def sign_out():
    ACCOUNT.unlink(missing_ok=True)


# --- Google sign-in through the website ---------------------------------------
def google_start(port: int) -> str:
    cfg = firebase_config()
    state = secrets.token_urlsafe(24)
    _pending_states[state] = time.time() + 600
    site = cfg.get("siteUrl") or "https://" + cfg.get("authDomain", "").replace(".firebaseapp.com", ".web.app")
    return f"{site.rstrip('/')}/app-login.html?port={port}&state={state}"


def google_finish(state: str, id_token: str, refresh_token: str) -> dict:
    if _pending_states.pop(state, 0) < time.time():
        raise AuthError("This sign-in link expired. Try again from the app.")
    users = _post(IDT + "lookup", {"idToken": id_token}).get("users", [])  # proves the token is real
    if not users:
        raise AuthError("Couldn't verify that Google account.")
    u = users[0]
    return _save({"localId": u["localId"], "email": u.get("email", ""), "displayName": u.get("displayName", ""),
                  "photoUrl": u.get("photoUrl", ""), "idToken": id_token, "refreshToken": refresh_token})
