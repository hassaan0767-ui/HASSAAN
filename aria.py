#!/usr/bin/env python3
"""
ARIA — one-file desktop assistant.

Everything lives in this single file on purpose, so there's nothing to
wire together and nothing to get out of sync:
  - a real desktop window with an animated HUD-style visual
  - real app/website launching on YOUR computer
  - optional voice input/output (works without it too — see below)
  - optional general AI chat, once you add your own API key

REQUIRED for the app to run at all:
    pip install requests

OPTIONAL (for voice — the app works fine without these, just no mic/speech):
    pip install pyttsx3 SpeechRecognition pyaudio

OPTIONAL (for general AI chat, i.e. "answer anything like Claude"):
    1. Get a key at https://console.anthropic.com
    2. Set it as an environment variable named ANTHROPIC_API_KEY
    Without this, ARIA still handles time/date/jokes/calculator/reminders/
    opening apps and websites perfectly — it just can't have open-ended
    conversations, because that genuinely requires calling a real AI model
    over the internet with a real account behind it.

Run:
    py aria.py
"""

import sys
import os

# --- CRITICAL fix for the "opens then instantly closes" .exe problem ---
# When PyInstaller builds with --windowed, Windows gives the app NO console,
# which means sys.stdout / sys.stderr are None. If ANY library tries to
# print or warn (even once, even something harmless), Python crashes with
# "NoneType has no attribute 'write'" and the window disappears instantly
# with zero error message. This must run before any other imports.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import re
import time
import math
import shutil
import random
import platform
import threading
import subprocess
import webbrowser
import urllib.parse
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime, timedelta

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    import speech_recognition as sr
    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False


# ============================================================
#  CONFIG
# ============================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-5"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# Google Gemini — a genuinely free alternative (no credit card needed).
# Get a key at https://aistudio.google.com/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-flash-latest"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_PROMPT = (
    "You are ARIA, a warm, witty, capable personal AI assistant inspired by "
    "Jarvis from Iron Man, running as a desktop app. Reply concisely "
    "(2-4 sentences unless asked for detail). The user often writes in Roman "
    "Urdu / Urdu-English mix — reply naturally in whichever language/style "
    "they used (Roman Urdu is fine). Be helpful, a little charming, and efficient."
)

OS_NAME = platform.system().lower()

PROGRAM_FILES = os.environ.get("PROGRAMFILES", r"C:\Program Files")
PROGRAM_FILES_X86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
LOCAL_APPDATA = os.environ.get("LOCALAPPDATA", "")

# name -> list of things to try, in order, until one works.
# Each entry is either a bare command (found via PATH) or a full path guess.
WINDOWS_APPS = {
    "notepad": ["notepad"],
    "calculator": ["calc"],
    "paint": ["mspaint"],
    "cmd": ["cmd"],
    "terminal": ["cmd"],
    "explorer": ["explorer"],
    "file explorer": ["explorer"],
    "task manager": ["taskmgr"],
    "control panel": ["control"],
    "settings": ["start ms-settings:"],
    "word": ["winword"],
    "excel": ["excel"],
    "powerpoint": ["powerpnt"],
    "chrome": ["chrome", rf"{PROGRAM_FILES}\Google\Chrome\Application\chrome.exe",
               rf"{PROGRAM_FILES_X86}\Google\Chrome\Application\chrome.exe"],
    "edge": ["msedge", rf"{PROGRAM_FILES_X86}\Microsoft\Edge\Application\msedge.exe"],
    "brave": ["brave", rf"{PROGRAM_FILES}\BraveSoftware\Brave-Browser\Application\brave.exe",
              rf"{PROGRAM_FILES_X86}\BraveSoftware\Brave-Browser\Application\brave.exe"],
    "firefox": ["firefox", rf"{PROGRAM_FILES}\Mozilla Firefox\firefox.exe"],
    "spotify": ["spotify", rf"{LOCAL_APPDATA}\Microsoft\WindowsApps\Spotify.exe",
                rf"{LOCAL_APPDATA}\Spotify\Spotify.exe"],
    "discord": ["discord", rf"{LOCAL_APPDATA}\Discord\Update.exe --processStart Discord.exe"],
    "vscode": ["code"], "vs code": ["code"], "code": ["code"],
    "whatsapp": [rf"{LOCAL_APPDATA}\Microsoft\WindowsApps\WhatsApp.exe"],
    "telegram": [rf"{LOCAL_APPDATA}\Telegram Desktop\Telegram.exe"],
}

MAC_APPS = {
    "notes": "Notes", "calculator": "Calculator", "chrome": "Google Chrome",
    "safari": "Safari", "word": "Microsoft Word", "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint", "spotify": "Spotify",
    "vscode": "Visual Studio Code", "vs code": "Visual Studio Code",
    "finder": "Finder", "terminal": "Terminal", "brave": "Brave Browser",
    "firefox": "Firefox", "discord": "Discord", "whatsapp": "WhatsApp",
    "telegram": "Telegram",
}

LINUX_APPS = {
    "calculator": "gnome-calculator", "chrome": "google-chrome", "files": "nautilus",
    "terminal": "gnome-terminal", "vscode": "code", "vs code": "code",
    "firefox": "firefox", "brave": "brave-browser", "discord": "discord",
}

WEBSITE_MAP = {
    "youtube": "https://youtube.com", "gmail": "https://mail.google.com",
    "mail": "https://mail.google.com", "google": "https://google.com",
    "whatsapp web": "https://web.whatsapp.com", "facebook": "https://facebook.com",
    "instagram": "https://instagram.com", "twitter": "https://x.com", "x": "https://x.com",
    "netflix": "https://netflix.com", "spotify web": "https://open.spotify.com",
    "maps": "https://maps.google.com", "google maps": "https://maps.google.com",
    "github": "https://github.com", "amazon": "https://amazon.com",
    "linkedin": "https://linkedin.com", "calendar": "https://calendar.google.com",
    "drive": "https://drive.google.com",
}


# ============================================================
#  FREE APIS (no signup / no API key needed for any of these)
# ============================================================

WEATHER_CODES = {
    0: "saaf aasman", 1: "kaafi saaf", 2: "thodi baadal", 3: "baadal chhaye hue",
    45: "dhundh (fog)", 48: "gehri dhundh", 51: "halki boonda-baandi", 53: "boonda-baandi",
    55: "tez boonda-baandi", 61: "halki baarish", 63: "baarish", 65: "tez baarish",
    71: "halki barfbaari", 73: "barfbaari", 75: "tez barfbaari", 80: "baarish ke jhonke",
    81: "tez baarish ke jhonke", 82: "shadeed baarish", 95: "tez aandhi-toofan (thunderstorm)",
}


def get_weather(city: str) -> str:
    if not REQUESTS_OK:
        return "'requests' install nahi hai."
    try:
        geo = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                            params={"name": city, "count": 1}, timeout=10).json()
        results = geo.get("results")
        if not results:
            return f"\"{city}\" location nahi mili, spelling check karein."
        r = results[0]
        lat, lon, place, country = r["latitude"], r["longitude"], r.get("name", city), r.get("country", "")
        w = requests.get("https://api.open-meteo.com/v1/forecast",
                          params={"latitude": lat, "longitude": lon, "current_weather": True}, timeout=10).json()
        cw = w.get("current_weather", {})
        temp, wind, code = cw.get("temperature"), cw.get("windspeed"), cw.get("weathercode")
        desc = WEATHER_CODES.get(code, "")
        return f"{place}, {country} mein abhi {temp}°C hai — {desc}. Hawa ki raftar {wind} km/h."
    except Exception as e:
        return f"Weather laane mein masla hua: {e}"


def get_wiki(topic: str) -> str:
    if not REQUESTS_OK:
        return "'requests' install nahi hai."
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(topic)}"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "ARIA-desktop-assistant"})
        if resp.status_code != 200:
            return f"\"{topic}\" ke baare mein kuch nahi mila."
        data = resp.json()
        extract = data.get("extract")
        if not extract:
            return f"\"{topic}\" ke baare mein kuch nahi mila."
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        return f"{extract}\n\n(Source: Wikipedia — {page_url})"
    except Exception as e:
        return f"Wikipedia se laane mein masla hua: {e}"


def get_currency(amount: float, frm: str, to: str) -> str:
    if not REQUESTS_OK:
        return "'requests' install nahi hai."
    try:
        resp = requests.get(f"https://open.er-api.com/v6/latest/{frm.upper()}", timeout=10).json()
        rates = resp.get("rates", {})
        if to.upper() not in rates:
            return f"\"{to}\" currency code samajh nahi aaya (jaise USD, PKR, EUR use karein)."
        result = amount * rates[to.upper()]
        return f"{amount} {frm.upper()} = {result:.2f} {to.upper()}"
    except Exception as e:
        return f"Currency convert karne mein masla hua: {e}"


def get_dictionary(word: str) -> str:
    if not REQUESTS_OK:
        return "'requests' install nahi hai."
    try:
        resp = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=10)
        if resp.status_code != 200:
            return f"\"{word}\" ka meaning nahi mila."
        data = resp.json()
        meanings = data[0].get("meanings", [])
        defs = meanings[0].get("definitions", []) if meanings else []
        if not defs:
            return f"\"{word}\" ka meaning nahi mila."
        part = meanings[0].get("partOfSpeech", "")
        return f"{word} ({part}): {defs[0].get('definition')}"
    except Exception as e:
        return f"Dictionary check karne mein masla hua: {e}"


def get_quote() -> str:
    if not REQUESTS_OK:
        return "'requests' install nahi hai."
    try:
        resp = requests.get("https://api.quotable.io/random", timeout=10).json()
        return f'"{resp.get("content")}" — {resp.get("author")}'
    except Exception as e:
        return f"Quote laane mein masla hua: {e}"


def get_news(topic: str = None) -> str:
    if not REQUESTS_OK:
        return "'requests' install nahi hai."
    try:
        import xml.etree.ElementTree as ET
        query = topic.strip() if topic else "Pakistan"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")[:5]
        if not items:
            return f"\"{query}\" ke baare mein koi news nahi mili."
        lines = [f"{i+1}. {it.findtext('title')}" for i, it in enumerate(items)]
        heading = f"Top news — {query}:" if topic else "Aaj ki top headlines:"
        return heading + "\n" + "\n".join(lines)
    except Exception as e:
        return f"News laane mein masla hua: {e}"


LANG_CODES = {
    "urdu": "ur", "english": "en", "arabic": "ar", "spanish": "es", "french": "fr",
    "german": "de", "chinese": "zh", "hindi": "hi", "turkish": "tr", "italian": "it",
    "portuguese": "pt", "russian": "ru", "japanese": "ja", "korean": "ko", "punjabi": "pa",
}


def translate_text(text: str, target: str) -> str:
    if not REQUESTS_OK:
        return "'requests' install nahi hai."
    code = LANG_CODES.get(target.strip().lower(), target.strip().lower())
    try:
        resp = requests.get("https://api.mymemory.translated.net/get",
                             params={"q": text, "langpair": f"en|{code}"}, timeout=10).json()
        translated = resp.get("responseData", {}).get("translatedText")
        return translated or "Translate nahi ho saka."
    except Exception as e:
        return f"Translate karne mein masla hua: {e}"


def get_crypto_price(coin: str) -> str:
    if not REQUESTS_OK:
        return "'requests' install nahi hai."
    coin_id = coin.strip().lower()
    aliases = {"btc": "bitcoin", "eth": "ethereum", "doge": "dogecoin", "sol": "solana", "xrp": "ripple"}
    coin_id = aliases.get(coin_id, coin_id)
    try:
        resp = requests.get("https://api.coingecko.com/api/v3/simple/price",
                             params={"ids": coin_id, "vs_currencies": "usd"}, timeout=10).json()
        price = resp.get(coin_id, {}).get("usd")
        if price is None:
            return f"\"{coin}\" naam ka crypto nahi mila — poora naam try karein, jaise 'bitcoin'."
        return f"{coin_id.title()} ki qeemat: ${price:,}"
    except Exception as e:
        return f"Crypto price laane mein masla hua: {e}"


def get_stock_price(symbol: str) -> str:
    if not REQUESTS_OK:
        return "'requests' install nahi hai."
    try:
        resp = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}",
                             timeout=10, headers={"User-Agent": "Mozilla/5.0"}).json()
        result = resp["chart"]["result"][0]
        price = result["meta"]["regularMarketPrice"]
        currency = result["meta"].get("currency", "")
        return f"{symbol.upper()} ka price: {price} {currency}"
    except Exception as e:
        return f"Stock price nahi mil saka: {e}"


# ============================================================
#  SYSTEM CONTROL — volume & brightness (Windows, zero extra installs)
# ============================================================

def _run_ps(cmd: str, timeout=10):
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           capture_output=True, text=True, timeout=timeout)


def get_brightness():
    if OS_NAME != "windows":
        return None
    try:
        r = _run_ps("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness")
        return int(r.stdout.strip())
    except Exception:
        return None


def set_brightness(pct) -> str:
    if OS_NAME != "windows":
        return "Brightness control abhi sirf Windows par kaam karta hai."
    pct = max(0, min(100, int(pct)))
    try:
        _run_ps(f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{pct})")
        return f"Brightness {pct}% par set kar diya."
    except Exception as e:
        return (f"Brightness set nahi ho saki: {e}\n"
                f"(Note: yeh sirf laptop built-in screens par kaam karta hai — "
                f"external/desktop monitors WMI se control nahi hote.)")


def adjust_brightness(direction: str, amount: int = 15) -> str:
    cur = get_brightness()
    if cur is None:
        return ("Brightness read nahi ho saki — yeh feature sirf laptop built-in "
                "screens par kaam karta hai jo DDC brightness support karte hain.")
    new_val = cur + amount if direction == "up" else cur - amount
    return set_brightness(new_val)


def _press_volume_key(vk_code: int, times: int = 1):
    import ctypes
    KEYEVENTF_KEYUP = 0x0002
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def adjust_volume(direction: str, steps: int = 4) -> str:
    if OS_NAME != "windows":
        return "Volume control abhi sirf Windows par kaam karta hai."
    VK_VOLUME_UP, VK_VOLUME_DOWN, VK_VOLUME_MUTE = 0xAF, 0xAE, 0xAD
    try:
        if direction == "mute":
            _press_volume_key(VK_VOLUME_MUTE, 1)
            return "Volume mute/unmute kar diya."
        if direction == "up":
            _press_volume_key(VK_VOLUME_UP, steps)
            return "Volume barha diya."
        if direction == "down":
            _press_volume_key(VK_VOLUME_DOWN, steps)
            return "Volume kam kar diya."
    except Exception as e:
        return f"Volume control mein masla: {e}"


def set_volume_absolute(pct) -> str:
    if OS_NAME != "windows":
        return "Volume control abhi sirf Windows par kaam karta hai."
    pct = max(0, min(100, int(pct)))
    VK_VOLUME_UP, VK_VOLUME_DOWN = 0xAF, 0xAE
    try:
        _press_volume_key(VK_VOLUME_DOWN, 50)             # reset to 0
        _press_volume_key(VK_VOLUME_UP, round(pct / 2))   # ~2% per key press
        return f"Volume takreeban {pct}% par set kar diya."
    except Exception as e:
        return f"Volume set karne mein masla: {e}"


# ============================================================
#  APP / WEBSITE LAUNCHING
# ============================================================

def _try_launch(candidate: str) -> bool:
    try:
        if OS_NAME == "windows":
            if candidate.startswith("start "):
                os.system(candidate)
            else:
                subprocess.Popen(candidate, shell=True)
        else:
            subprocess.Popen(candidate.split())
        return True
    except Exception:
        return False


def open_app(name: str) -> str:
    name = name.strip().lower()

    if OS_NAME == "windows":
        for key, candidates in WINDOWS_APPS.items():
            if key in name or name in key:
                for c in candidates:
                    if shutil.which(c.split()[0]) or os.path.exists(c) or c.startswith("start") or " " not in c:
                        if _try_launch(c if " " in c and c.startswith("start") else f'"{c}"' if os.path.exists(c) else c):
                            return f"{key.title()} khol raha hoon."
                # last resort: just try every candidate blindly
                for c in candidates:
                    if _try_launch(c):
                        return f"{key.title()} khol raha hoon."
        return (f"\"{name}\" mujhe apne known apps mein nahi mila. Is file mein "
                f"WINDOWS_APPS dictionary mein apna app aur uska exe path add kar dein.")

    elif OS_NAME == "darwin":
        for key, app in MAC_APPS.items():
            if key in name or name in key:
                try:
                    subprocess.Popen(["open", "-a", app])
                    return f"{key.title()} khol raha hoon."
                except Exception as e:
                    return f"{key.title()} open karne mein masla: {e}"
        return f"\"{name}\" mujhe apne known apps mein nahi mila."

    else:
        for key, cmd in LINUX_APPS.items():
            if key in name or name in key:
                try:
                    subprocess.Popen([cmd])
                    return f"{key.title()} khol raha hoon."
                except Exception as e:
                    return f"{key.title()} open karne mein masla: {e}"
        return f"\"{name}\" mujhe apne known apps mein nahi mila."


def open_website(name: str):
    name = name.strip().lower()
    for key, url in WEBSITE_MAP.items():
        if key in name:
            webbrowser.open(url)
            return f"{key.title()} khol raha hoon browser mein."
    if "." in name and " " not in name:
        url = name if name.startswith("http") else f"https://{name}"
        webbrowser.open(url)
        return f"{url} khol raha hoon."
    return None


# ============================================================
#  PHONE CONTROL (real Android phone via USB + ADB)
# ============================================================
# This genuinely opens apps on a physically connected Android phone.
# Requires: Android platform-tools (adb) installed and on PATH, USB
# debugging enabled on the phone, and the phone connected via USB cable
# with the "Allow USB debugging?" prompt accepted. See README.md.
# (iPhones cannot be controlled this way — Apple does not allow it.)

PHONE_APPS = {
    "whatsapp": "com.whatsapp",
    "youtube": "com.google.android.youtube",
    "instagram": "com.instagram.android",
    "chrome": "com.android.chrome",
    "gmail": "com.google.android.gm",
    "settings": "com.android.settings",
    "spotify": "com.spotify.music",
    "facebook": "com.facebook.katana",
    "maps": "com.google.android.apps.maps",
    "play store": "com.android.vending",
    "hotstar": "in.startv.hotstar",
    "jio hotstar": "in.startv.hotstar",
    "netflix": "com.netflix.mediaclient",
    "tiktok": "com.zhiliaoapp.musically",
    "telegram": "org.telegram.messenger",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
    "snapchat": "com.snapchat.android",
    "camera": "com.android.camera2",
    "gallery": "com.google.android.apps.photos",
    "photos": "com.google.android.apps.photos",
}


def _adb_available():
    return shutil.which("adb") is not None


def _adb_device_connected():
    try:
        out = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=8).stdout
        lines = [l.strip() for l in out.splitlines()[1:] if l.strip()]
        return any(l.endswith("device") for l in lines)
    except Exception:
        return False


def open_phone_app(name: str) -> str:
    name = name.strip().lower()

    if not _adb_available():
        return ("Phone control ke liye ADB install nahi hai is computer par. "
                "README.md mein 'Phone Control Setup' section dekhein.")
    if not _adb_device_connected():
        return ("Koi phone connected/authorized nahi mila. Check karein: USB cable "
                "lagi hai, phone par 'Allow USB debugging?' popup accept kiya hai, "
                "aur Developer Options mein USB debugging ON hai.")

    match = None
    for key, pkg in PHONE_APPS.items():
        if key in name or name in key:
            match = (key, pkg)
            break
    if not match:
        return (f"\"{name}\" phone ke known apps ki list mein nahi hai. "
                f"aria.py mein PHONE_APPS dictionary mein iska package name add karein.")

    key, pkg = match
    try:
        subprocess.run(
            ["adb", "shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"],
            capture_output=True, text=True, timeout=10,
        )
        return f"Phone par {key.title()} khol raha hoon."
    except Exception as e:
        return f"Phone par {key.title()} open karne mein masla: {e}"


def handle_phone_command(raw: str):
    m = re.match(
        r"^(?:open|launch|start|khol(?:o|do|dein)?)\s+(.+?)\s+(?:on|pe|par)\s+(?:my\s+)?phone$",
        raw.strip(), re.IGNORECASE,
    )
    if not m:
        m = re.match(r"^phone\s*[:\-]?\s*(?:open|khol(?:o|do|dein)?)\s+(.+)", raw.strip(), re.IGNORECASE)
    if not m:
        return None
    return open_phone_app(m.group(1).strip())


def handle_open_command(raw: str):
    phone_result = handle_phone_command(raw)
    if phone_result:
        return phone_result
    m = re.match(r"^(?:open|launch|start|khol(?:o|do|dein)?|chalao)\s+(.+)", raw.strip(), re.IGNORECASE)
    if not m:
        return None
    target = re.sub(r"^(the|app|website|site)\s+", "", m.group(1).strip().rstrip("."), flags=re.IGNORECASE)
    return open_website(target) or open_app(target)


# ============================================================
#  REMINDERS
# ============================================================

reminders = []  # (fire_time, note)


def start_reminder_watcher(on_fire):
    def loop():
        while True:
            now = datetime.now()
            due = [r for r in reminders if r[0] <= now]
            for r in due:
                on_fire(f"Reminder: {r[1]}")
                reminders.remove(r)
            time.sleep(5)
    threading.Thread(target=loop, daemon=True).start()


def parse_reminder(text: str):
    m = re.search(r"in\s+(\d+)\s*(second|minute|hour)s?\s*(?:to|for)?\s*(.*)", text, re.IGNORECASE)
    if m:
        n, unit, note = int(m.group(1)), m.group(2).lower(), m.group(3).strip()
        delta = {"second": timedelta(seconds=n), "minute": timedelta(minutes=n), "hour": timedelta(hours=n)}[unit]
        reminders.append((datetime.now() + delta, note or "Reminder"))
        return f"Theek hai, {n} {unit}(s) mein yaad dila doongi: \"{note or 'Reminder'}\""
    return None


# ============================================================
#  LOCAL INSTANT COMMANDS
# ============================================================

def try_local_command(raw: str):
    t = raw.strip().lower()

    if t in ("time", "what time is it") or "time kya" in t:
        return f"Abhi waqt hai: {datetime.now().strftime('%I:%M %p')}"
    if t in ("date", "today's date") or "tareekh" in t:
        return f"Aaj ki tareekh: {datetime.now().strftime('%A, %d %B %Y')}"
    if t == "joke":
        jokes = [
            "Main ek AI hoon, isliye mera sense of humor bhi thoda 'processed' hai.",
            "Ek robot ne kaha: main tumse pyaar karta hoon 0.001% error ke saath.",
            "Kabhi socha, agar Wi-Fi bhookh se mar jaye to kya hoga? Signal loss!",
        ]
        return random.choice(jokes)
    if t.startswith("calc") or re.fullmatch(r"[\d\s+\-*/().]+", t.replace("calculate", "")):
        expr = t.replace("calculate", "").replace("calc", "").strip()
        if expr and re.fullmatch(r"[\d\s+\-*/().]+", expr):
            try:
                return f"Result: {eval(expr, {'__builtins__': {}})}"
            except Exception:
                return "Yeh expression samajh nahi aaya, dobara likhein — jaise: 12*8+5"
        return "Calculate karne ke liye seedha likhein, jaise: 45*3"
    if t in ("remind me", "reminder", "yaad dila", "yaad dilana"):
        return "REMINDER_PROMPT"
    if "remind me" in t or t.startswith("yaad dila"):
        return parse_reminder(raw) or "Format istemal karein: \"remind me in 10 minutes to drink water\""
    if t in ("list reminders", "reminders"):
        if not reminders:
            return "Abhi koi reminder set nahi hai."
        return "\n".join(f"{i+1}. {note} ({when.strftime('%I:%M %p')})" for i, (when, note) in enumerate(reminders))

    if t in ("weather", "mausam"):
        return "WEATHER_PROMPT"
    m = re.match(r"^(?:weather|mausam)\s+(?:in|for)?\s*(.+)", raw.strip(), re.IGNORECASE)
    if m:
        return get_weather(m.group(1).strip())

    m = re.match(r"^convert\s+([\d.]+)\s+([a-zA-Z]{3})\s+to\s+([a-zA-Z]{3})", raw.strip(), re.IGNORECASE)
    if m:
        return get_currency(float(m.group(1)), m.group(2), m.group(3))

    m = re.match(r"^(?:meaning of|define)\s+(.+)", raw.strip(), re.IGNORECASE)
    if m:
        return get_dictionary(m.group(1).strip())

    if t in ("quote", "quote of the day"):
        return get_quote()

    if t in ("wiki", "wikipedia"):
        return "Kis topic ke bare mein jaanna hai? Jaise: 'wiki Pakistan'"

    m = re.match(r"^(?:wikipedia|wiki|who is|what is)\s+(.+)", raw.strip(), re.IGNORECASE)
    if m and not re.fullmatch(r"[\d\s+\-*/().]+", m.group(1)):
        return get_wiki(m.group(1).strip())

    m = re.match(r"^news(?:\s+(?:about|on|for)\s+(.+))?$", raw.strip(), re.IGNORECASE)
    if m:
        return get_news(m.group(1).strip() if m.group(1) else None)

    m = re.match(r"^translate\s+(.+?)\s+(?:to|into|mein)\s+(\w+)$", raw.strip(), re.IGNORECASE)
    if m:
        return translate_text(m.group(1).strip(), m.group(2).strip())

    m = re.match(r"^(?:price of|crypto price of|crypto)\s+(\w+)$", raw.strip(), re.IGNORECASE)
    if m:
        return get_crypto_price(m.group(1).strip())
    if re.search(r"\b(bitcoin|btc|ethereum|eth|dogecoin|doge|solana|sol)\b.*\bprice\b", t) or \
       re.search(r"\bprice\b.*\b(bitcoin|btc|ethereum|eth|dogecoin|doge|solana|sol)\b", t):
        coin_match = re.search(r"\b(bitcoin|btc|ethereum|eth|dogecoin|doge|solana|sol)\b", t)
        if coin_match:
            return get_crypto_price(coin_match.group(1))

    m = re.match(r"^stock(?:\s+price)?\s+(?:of\s+)?([a-zA-Z.]+)$", raw.strip(), re.IGNORECASE)
    if m:
        return get_stock_price(m.group(1).strip())

    if re.search(r"\bbrightness\b", t):
        m = re.search(r"(\d{1,3})", t)
        if m and ("set" in t or "to" in t):
            return set_brightness(int(m.group(1)))
        if re.search(r"\b(up|increase|barha)\b", t):
            return adjust_brightness("up")
        if re.search(r"\b(down|decrease|kam)\b", t):
            return adjust_brightness("down")
        return "Format: 'set brightness to 70', 'brightness up', ya 'brightness down'"

    if re.search(r"\b(volume|awaz)\b", t):
        if "mute" in t:
            return adjust_volume("mute")
        m = re.search(r"(\d{1,3})", t)
        if m and ("set" in t or "to" in t):
            return set_volume_absolute(int(m.group(1)))
        if re.search(r"\b(up|increase|barha)\b", t):
            return adjust_volume("up")
        if re.search(r"\b(down|decrease|kam)\b", t):
            return adjust_volume("down")
        return "Format: 'volume up', 'volume down', 'mute', ya 'set volume to 50'"

    opened = handle_open_command(raw)
    if opened:
        return opened
    return None


# ============================================================
#  AI BRAIN
# ============================================================

def ask_gemini(history):
    """Returns (reply_text, error_message). If GEMINI_API_KEY isn't set,
    returns (None, None) so the caller can silently try another provider."""
    if not GEMINI_API_KEY:
        return None, None
    contents = [
        {"role": ("model" if m["role"] == "assistant" else "user"),
         "parts": [{"text": m["content"]}]}
        for m in history
    ]
    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            headers={"content-type": "application/json"},
            json={"contents": contents, "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]}},
            timeout=30,
        )
        if resp.status_code != 200:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            return None, f"Gemini API ne error diya ({resp.status_code}): {detail}"
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None, "Gemini se koi jawab nahi mila."
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        return (text or None), (None if text else "Gemini ne khali jawab diya.")
    except Exception as e:
        return None, f"Gemini API se connect nahi ho paaya: {e}"


def ask_anthropic(history):
    """Returns (reply_text, error_message)."""
    if not ANTHROPIC_API_KEY:
        return None, None
    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": ANTHROPIC_MODEL, "max_tokens": 500, "system": SYSTEM_PROMPT, "messages": history},
            timeout=30,
        )
        if resp.status_code != 200:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            return None, f"Anthropic API ne error diya ({resp.status_code}): {detail}"
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
        return (text or None), (None if text else "Anthropic ne khali jawab diya.")
    except Exception as e:
        return None, f"Anthropic API se connect nahi ho paaya: {e}"


def ask_brain(history):
    if not REQUESTS_OK:
        return "'requests' library install nahi hai — 'pip install requests' chalayein."

    errors = []

    # Try Gemini first — it's free, so this is the default path when configured.
    text, err = ask_gemini(history)
    if text:
        return text
    if err:
        errors.append(f"Gemini: {err}")

    # Fall back to Anthropic if Gemini isn't set up or failed.
    text, err = ask_anthropic(history)
    if text:
        return text
    if err:
        errors.append(f"Anthropic: {err}")

    if errors:
        # Show every provider that was actually tried and why it failed,
        # instead of silently hiding the first one — this is what makes it
        # possible to tell "Gemini key is wrong" apart from "Anthropic has
        # no credit" when both are configured.
        return "\n".join(errors)

    return (
        "Mujhe general baaton ke liye ek AI key chahiye. Do options hain:\n"
        "1) FREE: aistudio.google.com se Gemini key banayein, phir:\n"
        "   setx GEMINI_API_KEY \"your-key-here\"\n"
        "2) PAID: console.anthropic.com se Anthropic key banayein, phir:\n"
        "   setx ANTHROPIC_API_KEY \"your-key-here\"\n"
        "Key set karne ke baad app restart karein."
    )


# ============================================================
#  VOICE (optional) — Microsoft's free neural voice, with a fallback
# ============================================================

try:
    import edge_tts
    import asyncio
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    from playsound import playsound
    PLAYSOUND_AVAILABLE = True
except ImportError:
    PLAYSOUND_AVAILABLE = False

# A genuinely natural-sounding free Microsoft neural voice (needs internet).
# "Aria" felt like the right pick for an assistant named ARIA.
EDGE_VOICE = "en-US-AriaNeural"
NATURAL_VOICE_READY = EDGE_TTS_AVAILABLE and PLAYSOUND_AVAILABLE


def _speak_natural(text: str) -> bool:
    """Generates real neural speech via Microsoft Edge's free TTS service
    and plays it. Returns False (silently) if unavailable/offline, so the
    caller can fall back to the older robotic voice instead of erroring."""
    if not NATURAL_VOICE_READY:
        return False
    tmp_path = None
    try:
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        async def _generate():
            communicate = edge_tts.Communicate(text, EDGE_VOICE)
            await communicate.save(tmp_path)

        asyncio.run(_generate())
        playsound(tmp_path)
        return True
    except Exception:
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


class Voice:
    """Speaks using the natural neural voice when possible; automatically
    falls back to the basic offline voice (pyttsx3) if there's no internet
    or the neural packages aren't installed — so the app never goes silent.

    The offline engine is created LAZILY (only on first actual use) instead
    of at startup, since pyttsx3.init() can take a noticeable moment — and
    most replies use the online neural voice anyway, so most of the time
    this fallback is never even touched."""

    def __init__(self):
        self.engine = None
        self._engine_attempted = False

    def _ensure_engine(self):
        if self._engine_attempted:
            return
        self._engine_attempted = True
        if TTS_AVAILABLE:
            try:
                self.engine = pyttsx3.init()
                voices = self.engine.getProperty("voices")
                for v in voices:
                    if any(k in v.name.lower() for k in ("zira", "female", "hazel", "samantha")):
                        self.engine.setProperty("voice", v.id)
                        break
                self.engine.setProperty("rate", 165)
                self.engine.setProperty("volume", 1.0)
            except Exception:
                self.engine = None

    def say(self, text):
        if _speak_natural(text):
            return
        self._ensure_engine()
        if self.engine:
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception:
                pass


class Ears:
    def __init__(self):
        self.recognizer = sr.Recognizer() if STT_AVAILABLE else None
        self.mic_ok = False
        self._checked = False

    def _ensure_mic_checked(self):
        if self._checked:
            return
        self._checked = True
        if STT_AVAILABLE:
            try:
                sr.Microphone()
                self.mic_ok = True
            except Exception:
                self.mic_ok = False

    def listen_once(self, timeout=6):
        self._ensure_mic_checked()
        if not (STT_AVAILABLE and self.mic_ok):
            return None
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.4)
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=12)
            except Exception:
                return None
        try:
            return self.recognizer.recognize_google(audio)
        except Exception:
            return None


# ============================================================
#  GUI
# ============================================================

BG = "#04070d"
PANEL = "#0b1220"
LINE = "#132133"
CYAN = "#57e6f5"
CYAN_SOFT = "#1f4650"
AMBER = "#ffb454"
TEXT = "#e3eef6"
TEXT_DIM = "#6c8299"


class ARIAApp:
    def __init__(self, root):
        self.root = root
        root.title("ARIA — Personal AI Companion")
        root.geometry("880x760")
        root.configure(bg=BG)
        root.minsize(600, 560)

        self.voice = Voice()
        self.ears = Ears()
        self.history = []
        self.awaiting_reminder = False
        self.awaiting_weather_city = False

        start_reminder_watcher(lambda msg: self.root.after(0, self._reminder_fired, msg))

        # ---- Bottom-anchored widgets FIRST so they can never be pushed off-screen ----
        self._build_input_bar()
        self._build_quick_chips()
        self._build_footer()

        # ---- Then the expanding middle content ----
        self._build_header()
        self._build_canvas()
        self._build_log()

        self._start_animation()
        self._greet()

    # ---------------- sections ----------------
    def _build_header(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(14, 4), side="top")
        title_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        tk.Label(header, text="●  ARIA", fg=CYAN, bg=BG, font=title_font).pack(side="left")
        brain = "AI BRAIN: READY" if (GEMINI_API_KEY or ANTHROPIC_API_KEY) else "AI BRAIN: NOT SET"
        voice_status = "VOICE: READY" if (TTS_AVAILABLE) else "VOICE: OFF"
        tk.Label(header, text=f"{voice_status}   ·   {brain}", fg=TEXT_DIM, bg=BG,
                 font=("Consolas", 9)).pack(side="right")

    def _build_canvas(self):
        self.canvas = tk.Canvas(self.root, height=210, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="x", side="top")
        self.core_label = tk.Label(self.root, text="standing by", fg=TEXT_DIM, bg=BG, font=("Consolas", 9))
        self.core_label.pack(side="top", pady=(2, 4))

    def _build_log(self):
        log_frame = tk.Frame(self.root, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(4, 8), side="top")
        self.log = tk.Text(log_frame, bg="#070c15", fg=TEXT, insertbackground=TEXT,
                            font=("Segoe UI", 11), wrap="word", relief="flat",
                            padx=14, pady=12, state="disabled", borderwidth=0)
        self.log.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(log_frame, command=self.log.yview, troughcolor=BG, bg=PANEL)
        sb.pack(side="right", fill="y")
        self.log.config(yscrollcommand=sb.set)
        self.log.tag_config("user_who", foreground=AMBER, font=("Consolas", 8, "bold"))
        self.log.tag_config("bot_who", foreground=CYAN, font=("Consolas", 8, "bold"))
        self.log.tag_config("sys_who", foreground=TEXT_DIM, font=("Consolas", 8, "italic"))
        self.log.tag_config("body", foreground=TEXT, font=("Segoe UI", 11))

    def _build_quick_chips(self):
        chip_frame = tk.Frame(self.root, bg=BG)
        chip_frame.pack(fill="x", padx=20, pady=(0, 6), side="bottom")
        chips = [("⏱ Time", "time"), ("📅 Date", "date"), ("😄 Joke", "joke"),
                 ("📝 Notepad", "open notepad"), ("🌐 Chrome", "open chrome"),
                 ("⏰ Reminder", "remind me"), ("🌤 Weather", "weather"),
                 ("📰 News", "news"), ("₿ Bitcoin", "price of bitcoin"),
                 ("💬 Quote", "quote")]
        for label, cmd in chips:
            tk.Button(chip_frame, text=label, bg=PANEL, fg=CYAN, activebackground=CYAN_SOFT,
                      activeforeground=CYAN, relief="flat", font=("Consolas", 9), padx=9, pady=4,
                      cursor="hand2", command=lambda c=cmd: self._send(c)).pack(side="left", padx=4)

    def _build_input_bar(self):
        bar = tk.Frame(self.root, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        bar.pack(fill="x", padx=20, pady=(0, 4), side="bottom")
        self.entry = tk.Entry(bar, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
                               font=("Segoe UI", 12))
        self.entry.pack(side="left", fill="both", expand=True, padx=14, pady=11)
        self.entry.bind("<Return>", lambda e: self._on_send())
        mic_state = "normal" if STT_AVAILABLE else "disabled"
        self.mic_btn = tk.Button(bar, text="🎙", bg=PANEL, fg=CYAN, relief="flat", font=("Segoe UI", 14),
                                  state=mic_state, cursor="hand2", command=self._on_mic)
        self.mic_btn.pack(side="left", padx=3)
        tk.Button(bar, text="➤", bg=CYAN, fg="#04252a", relief="flat", font=("Segoe UI", 13, "bold"),
                  cursor="hand2", command=self._on_send).pack(side="left", padx=(3, 10))

    def _build_footer(self):
        note = "" if REQUESTS_OK else "  ⚠ 'requests' not installed — run: pip install requests"
        tk.Label(self.root, text=f'TYPE "OPEN [APP]" TO LAUNCH REAL PROGRAMS{note}',
                 fg="#37475a", bg=BG, font=("Consolas", 9)).pack(side="bottom", pady=(0, 8))

    # ---------------- animation ----------------
    def _start_animation(self):
        self.angle = 0.0
        self.particles = [{"x": random.random(), "y": random.random(),
                            "r": random.uniform(1, 2.6), "spd": random.uniform(0.15, 0.5)}
                           for _ in range(34)]
        self.state = "idle"
        self._animate()

    def _lerp_color(self, c1, c2, t):
        c1 = tuple(int(c1[i:i+2], 16) for i in (1, 3, 5))
        c2 = tuple(int(c2[i:i+2], 16) for i in (1, 3, 5))
        mix = tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3))
        return f"#{mix[0]:02x}{mix[1]:02x}{mix[2]:02x}"

    def _animate(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width() or 880
        h = c.winfo_height() or 210
        cx, cy = w / 2, h / 2

        for gx in range(0, w, 30):
            for gy in range(0, h, 26):
                c.create_oval(gx, gy, gx + 1, gy + 1, fill=LINE, outline="")

        for p in self.particles:
            p["y"] -= p["spd"] * 0.004
            if p["y"] < 0:
                p["y"], p["x"] = 1, random.random()
            px, py = p["x"] * w, p["y"] * h
            c.create_oval(px, py, px + p["r"], py + p["r"], fill=AMBER, outline="")

        self.angle = (self.angle + (3.4 if self.state != "idle" else 1.6)) % 360
        rings = [(70, CYAN, None), (54, AMBER, (5, 4)), (38, CYAN_SOFT, (2, 3))]
        for i, (rad, color, dash) in enumerate(rings):
            start = self.angle * (1 if i % 2 == 0 else -1.2) + i * 50
            kwargs = dict(start=start, extent=250, style="arc", outline=color, width=2)
            if dash:
                kwargs["dash"] = dash
            c.create_arc(cx - rad, cy - rad, cx + rad, cy + rad, **kwargs)

        pulse_speed = 6 if self.state in ("thinking", "speaking") else 20
        base_r = (20 if self.state == "listening" else 18) + 3 * math.sin(self.angle / pulse_speed)
        base_color = AMBER if self.state == "listening" else CYAN
        for i in range(6, 0, -1):
            t = i / 6
            r = base_r + i * 6
            col = self._lerp_color(BG, base_color, 1 - t * 0.85)
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")
        c.create_oval(cx - base_r, cy - base_r, cx + base_r, cy + base_r, fill="#eafcff", outline="")

        self.root.after(35, self._animate)

    def _set_state(self, state):
        self.state = state
        self.core_label.config(text={"idle": "standing by", "thinking": "thinking",
                                      "speaking": "responding", "listening": "listening"}.get(state, state))

    # ---------------- chat ----------------
    def _append(self, who, text):
        self.log.config(state="normal")
        label = {"user": "YOU", "bot": "ARIA", "sys": "SYSTEM"}[who]
        self.log.insert("end", f"{label}\n", f"{who}_who")
        self.log.insert("end", f"{text}\n\n", "body")
        self.log.see("end")
        self.log.config(state="disabled")

    def _greet(self):
        greet = "Assalam-o-Alaikum! Main ARIA hoon. Boliye ya likhiye — main sun rahi hoon."
        self._append("bot", greet)
        threading.Thread(target=self.voice.say, args=(greet,), daemon=True).start()

    def _reminder_fired(self, text):
        self._append("sys", text)
        threading.Thread(target=self.voice.say, args=(text,), daemon=True).start()

    def _on_send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._send(text)

    def _send(self, raw):
        self._append("user", raw)

        if self.awaiting_reminder:
            self.awaiting_reminder = False
            reminders.append((datetime.now(), raw))
            reply = f'Theek hai, yaad rakh liya: "{raw}"'
            self._append("bot", reply)
            threading.Thread(target=self.voice.say, args=(reply,), daemon=True).start()
            return

        if self.awaiting_weather_city:
            self.awaiting_weather_city = False
            self._set_state("thinking")
            threading.Thread(target=self._weather_bg, args=(raw,), daemon=True).start()
            return

        self._set_state("thinking")
        threading.Thread(target=self._local_or_brain_bg, args=(raw,), daemon=True).start()

    def _weather_bg(self, city):
        reply = get_weather(city)
        self.root.after(0, self._local_result, reply)

    def _local_or_brain_bg(self, raw):
        # runs off the UI thread since some local commands call the network (weather/wiki/etc.)
        local = try_local_command(raw)
        if local == "REMINDER_PROMPT":
            self.root.after(0, self._prompt_reminder)
            return
        if local == "WEATHER_PROMPT":
            self.root.after(0, self._prompt_weather)
            return
        if local:
            self.root.after(0, self._local_result, local)
            return
        reply = ask_brain(self._history_with(raw))
        self.history.append({"role": "user", "content": raw})
        self.history.append({"role": "assistant", "content": reply})
        self.root.after(0, self._brain_done, reply)

    def _history_with(self, raw):
        return self.history + [{"role": "user", "content": raw}]

    def _local_result(self, text):
        self._append("bot", text)
        threading.Thread(target=self.voice.say, args=(text,), daemon=True).start()
        self._set_state("idle")

    def _prompt_reminder(self):
        self.awaiting_reminder = True
        reply = "Kya yaad rakhwana hai? Likh dein."
        self._append("bot", reply)
        threading.Thread(target=self.voice.say, args=(reply,), daemon=True).start()
        self._set_state("idle")

    def _prompt_weather(self):
        self.awaiting_weather_city = True
        reply = "Konsa shehar? Naam likh dein."
        self._append("bot", reply)
        threading.Thread(target=self.voice.say, args=(reply,), daemon=True).start()
        self._set_state("idle")

    def _brain_done(self, reply):
        self._append("bot", reply)
        self._set_state("speaking")
        threading.Thread(target=self._speak_then_idle, args=(reply,), daemon=True).start()

    def _speak_then_idle(self, text):
        self.voice.say(text)
        self.root.after(0, self._set_state, "idle")

    def _on_mic(self):
        self._set_state("listening")
        threading.Thread(target=self._listen_bg, daemon=True).start()

    def _listen_bg(self):
        spoken = self.ears.listen_once()
        self.root.after(0, self._set_state, "idle")
        if spoken:
            self.root.after(0, self._send, spoken)
        else:
            self.root.after(0, self._append, "sys", "Kuch sunayi nahi diya, dobara koshish karein.")


def main():
    try:
        root = tk.Tk()
        ARIAApp(root)
        root.mainloop()
    except Exception:
        import traceback
        error_text = traceback.format_exc()
        # Write to a log file next to the app so we can see exactly what broke
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "aria_error.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(error_text)
        except Exception:
            log_path = None
        # Show a real dialog instead of silently vanishing
        try:
            from tkinter import messagebox
            messagebox.showerror(
                "ARIA crashed",
                "ARIA ek error ki wajah se band ho gaya.\n\n"
                + error_text[-800:]
                + (f"\n\nPoori detail is file mein hai:\n{log_path}" if log_path else "")
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
