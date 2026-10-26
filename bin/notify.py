#!/usr/bin/env python3
"""Сообщение вам в Telegram через вашего бота. Без бота — печатает в терминал.

Настройка (один из вариантов):
  • переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID
  • файл ~/.config/job-search/telegram.json: {"token": "...", "chat_id": "..."}
Как получить токен и chat_id — docs/SETUP.md.

Из кода:
    from notify import notify
    notify("текст")                      # просто отправить
    notify("текст", key="hh-chat-123")   # не повторять одно и то же: ключ запоминается

Из терминала:
    python3 bin/notify.py "текст"
    python3 bin/notify.py --key reply-acme "Acme ждёт ответа в чате hh: <ссылка>"

Правило: одно сообщение — одно дело, со ссылкой на место действия. Пустых «всё тихо»
не слать, иначе канал обесценится к моменту, когда придёт важное.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("JOBSEARCH_DATA", os.path.join(ROOT, "data"))
SEEN = os.path.join(DATA, "log", "notified.json")
CONF = os.path.expanduser("~/.config/job-search/telegram.json")


def _creds():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        return token, chat
    try:
        with open(CONF, encoding="utf-8") as f:
            c = json.load(f)
        return c["token"], str(c["chat_id"])
    except (OSError, KeyError, ValueError):
        return None, None


def _seen():
    try:
        with open(SEEN, encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def notify(text, key=None):
    """Отправить сообщение. Возвращает True, если ушло (или напечатано без бота)."""
    if key:
        seen = _seen()
        if key in seen:
            return False
    token, chat = _creds()
    if not token:
        print(f"[telegram не настроен] {text}")
        return True
    data = urllib.parse.urlencode({"chat_id": chat, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        ok = json.load(r).get("ok", False)
    if ok and key:
        os.makedirs(os.path.dirname(SEEN), exist_ok=True)
        seen = _seen()
        seen.add(key)
        with open(SEEN, "w", encoding="utf-8") as f:
            json.dump(sorted(seen), f, ensure_ascii=False)
    return ok


if __name__ == "__main__":
    args = sys.argv[1:]
    key = None
    if args[:1] == ["--key"] and len(args) >= 3:
        key, args = args[1], args[2:]
    if not args:
        sys.exit(__doc__)
    sys.exit(0 if notify(" ".join(args), key=key) else 1)
