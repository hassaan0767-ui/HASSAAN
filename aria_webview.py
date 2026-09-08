#!/usr/bin/env python3
"""
ARIA — Dashboard (high-fidelity graphics) version.

This shows a MAYA-OS-style animated dashboard (globe visualizer, gauges,
module panel, live monitor graph) inside a REAL desktop window, using
pywebview. All the actual intelligence — opening real apps, reminders,
weather/news/crypto/etc., the AI brain — is the exact same code as
aria.py; this file only adds the window + wires the HTML to it.

Run:
    py aria_webview.py

Needs:
    pip install pywebview
(On Windows this uses the Edge WebView2 runtime, already built into
Windows 10/11. If missing: https://developer.microsoft.com/microsoft-edge/webview2/)

If this window fails to open, use `py aria.py` instead — that version
has simpler graphics but no extra dependency and is guaranteed to run.
"""

import os
import re
import sys
import json
import time
import hashlib
import secrets
import requests
from datetime import datetime

import webview

from aria import (
    try_local_command, ask_brain, reminders,
    start_reminder_watcher, Ears, Voice, ANTHROPIC_API_KEY, GEMINI_API_KEY, NATURAL_VOICE_READY,
)

FIREBASE_DB_URL = "https://aria-7d174-default-rtdb.firebaseio.com"


def resource_path(filename):
    """Works both when run normally and when frozen into a PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


def user_data_path(filename):
    """Where saved data (account file, etc.) lives — next to the .exe/script,
    NOT inside the PyInstaller temp bundle, so it survives between runs."""
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base, filename)


HTML_PATH = resource_path("aria_ui.html")
USERS_PATH = user_data_path("aria_users.json")

# ============================================================
#  ACCOUNT SECURITY
# ============================================================
# Local-only accounts (no internet/server involved). Passwords are never
# stored in plain text — only a salted PBKDF2 hash. A strict password
# policy blocks trivial combinations like admin/admin, and repeated failed
# logins are throttled to slow down guessing.

COMMON_WEAK_PASSWORDS = {
    "admin", "admin123", "password", "password1", "12345678", "123456789",
    "qwerty123", "letmein", "welcome1", "changeme", "iloveyou", "abc12345",
    "111111111", "00000000",
}

PBKDF2_ITERATIONS = 200_000
_failed_attempts = {}   # username -> (count, last_attempt_ts), in-memory per session


def _load_users():
    if not os.path.exists(USERS_PATH):
        return {}
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_users(users):
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f)


def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS).hex()


def _password_policy_error(username: str, password: str):
    if len(password) < 8:
        return "Password kam se kam 8 characters ka hona chahiye."
    if not re.search(r"[A-Za-z]", password):
        return "Password mein kam se kam ek letter hona chahiye."
    if not re.search(r"[0-9]", password):
        return "Password mein kam se kam ek number hona chahiye."
    if password.lower() in COMMON_WEAK_PASSWORDS:
        return "Yeh password bohot aam hai (jaise 'admin' ya 'password') — koi behtar password chunein."
    if password.lower() == username.strip().lower():
        return "Password username jaisa nahi ho sakta."
    if username.strip().lower() == "admin" and password.lower().startswith("admin"):
        return "'admin' username ke saath itna simple password istemal na karein."
    return None


class AuthApi:
    def has_account(self) -> bool:
        return len(_load_users()) > 0

    def sign_up(self, username: str, password: str, confirm: str):
        username = (username or "").strip()
        if not username or len(username) < 3:
            return {"ok": False, "error": "Username kam se kam 3 characters ka hona chahiye."}
        if password != confirm:
            return {"ok": False, "error": "Dono passwords match nahi karte."}
        err = _password_policy_error(username, password)
        if err:
            return {"ok": False, "error": err}

        users = _load_users()
        if username.lower() in {u.lower() for u in users}:
            return {"ok": False, "error": "Yeh username pehle se maujood hai."}

        salt = secrets.token_hex(16)
        users[username] = {"salt": salt, "hash": _hash_password(password, salt)}
        _save_users(users)
        return {"ok": True}

    def login(self, username: str, password: str):
        username = (username or "").strip()
        now = time.time()
        count, last_ts = _failed_attempts.get(username.lower(), (0, 0))

        # simple throttle: after 5 failed tries, force a growing wait
        if count >= 5:
            wait_needed = min(60, 2 ** (count - 4))
            if now - last_ts < wait_needed:
                remaining = int(wait_needed - (now - last_ts))
                return {"ok": False, "error": f"Bohot dafa ghalat koshish hui. {remaining} second wait karein."}

        users = _load_users()
        record = None
        for uname, data in users.items():
            if uname.lower() == username.lower():
                record = data
                break

        if not record or _hash_password(password, record["salt"]) != record["hash"]:
            _failed_attempts[username.lower()] = (count + 1, now)
            return {"ok": False, "error": "Username ya password ghalat hai."}

        _failed_attempts.pop(username.lower(), None)
        return {"ok": True}


class Api(AuthApi):
    def __init__(self):
        self.history = []
        self.chat_log = []  # full visual transcript (every message shown on screen)
        self.ears = Ears()
        self.voice = Voice()  # now uses the natural neural voice, same as aria.py
        self.firebase_uid = None
        self.firebase_token = None
        self.firebase_email = None

    def local_command(self, raw: str):
        return try_local_command(raw)

    def set_cloud_user(self, uid: str, id_token: str, email: str):
        """Called from JS right after a successful Firebase login/signup.
        Pulls any reminders AND chat history already saved in the cloud for
        this account so they're available even on a brand-new computer."""
        self.firebase_uid = uid
        self.firebase_token = id_token
        self.firebase_email = email

        try:
            resp = requests.get(
                f"{FIREBASE_DB_URL}/users/{uid}/reminders.json",
                params={"auth": id_token},
                timeout=10,
            )
            if resp.status_code == 200 and resp.json():
                reminders.clear()
                for _key, item in resp.json().items():
                    try:
                        fire_at = datetime.fromisoformat(item["fire_at"])
                        reminders.append((fire_at, item["note"]))
                    except Exception:
                        continue
        except Exception:
            pass  # cloud sync is best-effort — app still works fully offline

        try:
            resp = requests.get(
                f"{FIREBASE_DB_URL}/users/{uid}/chat_history.json",
                params={"auth": id_token},
                timeout=10,
            )
            if resp.status_code == 200 and resp.json():
                self.history = resp.json()
        except Exception:
            pass

        try:
            resp = requests.get(
                f"{FIREBASE_DB_URL}/users/{uid}/chat_log.json",
                params={"auth": id_token},
                timeout=10,
            )
            if resp.status_code == 200 and resp.json():
                self.chat_log = resp.json()
        except Exception:
            pass

        return {"ok": True, "email": email}

    def get_chat_history(self):
        return self.history

    def get_chat_log(self):
        return self.chat_log

    def log_message(self, who: str, text: str) -> bool:
        """Called from JS for every user/bot bubble shown on screen — this
        covers EVERYTHING (weather, news, apps opened, AI chat, etc.), not
        just AI conversations, so the whole visual history restores after
        closing and reopening the app."""
        self.chat_log.append({"who": who, "text": text})
        self.chat_log = self.chat_log[-150:]  # keep it from growing forever
        if self.firebase_uid:
            try:
                requests.put(
                    f"{FIREBASE_DB_URL}/users/{self.firebase_uid}/chat_log.json",
                    params={"auth": self.firebase_token},
                    json=self.chat_log,
                    timeout=10,
                )
            except Exception:
                pass
        return True

    def _sync_chat_history(self):
        if not self.firebase_uid:
            return
        try:
            requests.put(
                f"{FIREBASE_DB_URL}/users/{self.firebase_uid}/chat_history.json",
                params={"auth": self.firebase_token},
                json=self.history[-60:],  # keep the cloud copy from growing forever
                timeout=10,
            )
        except Exception:
            pass  # chat still works locally even if the cloud save fails

    def submit_reminder(self, note: str) -> str:
        note = (note or "").strip() or "Reminder"
        fire_at = datetime.now()
        reminders.append((fire_at, note))

        if self.firebase_uid:
            try:
                requests.post(
                    f"{FIREBASE_DB_URL}/users/{self.firebase_uid}/reminders.json",
                    params={"auth": self.firebase_token},
                    json={"note": note, "fire_at": fire_at.isoformat()},
                    timeout=10,
                )
            except Exception:
                pass  # local reminder still works even if the cloud save fails

        return f'Theek hai, yaad rakh liya: "{note}"'

    def ask_ai(self, raw: str) -> str:
        self.history.append({"role": "user", "content": raw})
        reply = ask_brain(self.history)
        self.history.append({"role": "assistant", "content": reply})
        self._sync_chat_history()
        return reply

    def reset_history(self):
        self.history = []
        self.chat_log = []
        self._sync_chat_history()
        if self.firebase_uid:
            try:
                requests.put(
                    f"{FIREBASE_DB_URL}/users/{self.firebase_uid}/chat_log.json",
                    params={"auth": self.firebase_token},
                    json=[],
                    timeout=10,
                )
            except Exception:
                pass
        return True

    def listen(self):
        return self.ears.listen_once()

    def speak_text(self, text: str) -> bool:
        """Called from JS. Fires speech playback on a background thread and
        returns immediately — the app no longer waits for the audio to
        finish before it's usable again, which is what was making every
        reply feel slow."""
        import threading
        threading.Thread(target=self.voice.say, args=(text,), daemon=True).start()
        return True

    def get_status(self):
        return {
            "brain_ready": bool(GEMINI_API_KEY or ANTHROPIC_API_KEY),
            "reminder_count": len(reminders),
            "voice_ready": bool(NATURAL_VOICE_READY),
        }

    def list_users(self):
        """Returns every signed-up email (never passwords — Firebase makes
        real passwords impossible to retrieve, by design). Needs a Firebase
        Admin service account key — see README's Firebase section."""
        try:
            import firebase_admin
            from firebase_admin import credentials, auth as fb_admin_auth
        except ImportError:
            return {"ok": False, "error": "'firebase-admin' install nahi hai. Chalayein: pip install firebase-admin"}

        key_path = user_data_path("serviceAccountKey.json")
        if not os.path.exists(key_path):
            return {"ok": False, "error": "serviceAccountKey.json nahi mili. README.md ka 'Users Panel Setup' section dekhein."}

        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred)

            users = []
            for u in fb_admin_auth.list_users().iterate_all():
                created = u.user_metadata.creation_timestamp
                last_login = u.user_metadata.last_sign_in_timestamp
                users.append({
                    "email": u.email or "(no email)",
                    "created": datetime.fromtimestamp(created / 1000).strftime("%d %b %Y, %I:%M %p") if created else "—",
                    "last_login": datetime.fromtimestamp(last_login / 1000).strftime("%d %b %Y, %I:%M %p") if last_login else "Never",
                })
            return {"ok": True, "users": users}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def main():
    try:
        api = Api()
        start_reminder_watcher(api.voice)

        webview.create_window(
            "ARIA — Personal AI Companion",
            HTML_PATH,
            js_api=api,
            width=1180,
            height=760,
            min_size=(900, 620),
            background_color="#03060b",
        )
        # private_mode=True (pywebview's default) wipes all storage between
        # runs — like Incognito — which is exactly why the login session and
        # anything else saved in the browser wasn't surviving a restart.
        # storage_path gives it a real, persistent folder to keep that data in.
        webview.start(private_mode=False, storage_path=user_data_path("webview_storage"))
    except Exception:
        import traceback
        error_text = traceback.format_exc()
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "aria_error.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(error_text)
        except Exception:
            log_path = None
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "ARIA crashed",
                "ARIA (dashboard) ek error ki wajah se band ho gaya.\n\n"
                + error_text[-800:]
                + (f"\n\nPoori detail:\n{log_path}" if log_path else "")
                + "\n\nAgar yeh baar-baar ho, 'py aria.py' try karein (simpler fallback)."
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
