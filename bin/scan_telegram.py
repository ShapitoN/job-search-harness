#!/usr/bin/env python3
"""
scan_telegram.py — разведка публичных Telegram-каналов без участия модели.

Зачем: читать ленты каналов моделью дорого, а полезных постов там единицы. Эту работу —
«сходить, посмотреть, что нового, выкинуть мусор» — делает скрипт за один вызов.
Агенту остаётся оценить десяток строк, а не читать ленты.

Что делает: качает t.me/s/<канал>, берёт только посты новее последнего виденного,
отсеивает по стоп-словам, оставляет то, что похоже на вашу роль, вытаскивает зарплату,
@-контакты и почту, печатает компактную таблицу. Позиции запоминает, поэтому следующий
запуск читает только новое.

Настройка — config/search.json (скопируйте из config/search.example.json):
  telegram_channels  {"регион": ["канал1", "канал2"]}
  role_keywords      список регулярных выражений: что считаем подходящим постом
  stop_keywords      список регулярных выражений: явный мусор

Использование:
  scan_telegram.py --region main          # обойти каналы региона
  scan_telegram.py --region main --all    # не фильтровать по ключевым словам роли
  scan_telegram.py --region main --dry-run
  scan_telegram.py --list                 # какие каналы в обходе и где остановились
  scan_telegram.py --reset <канал>        # перечитать канал с нуля
"""

import argparse
import html as htmlmod
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("JOBSEARCH_DATA", os.path.join(ROOT, "data"))
STATE_PATH = os.path.join(DATA, "log", "telegram-positions.json")
CONFIG_PATH = os.environ.get("JOBSEARCH_CONFIG", os.path.join(ROOT, "config", "search.json"))


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise SystemExit(f"нет {CONFIG_PATH} — скопируйте config/search.example.json и заполните")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


CFG = load_config()
CHANNELS = CFG.get("telegram_channels", {})
GOOD = re.compile("(" + "|".join(CFG.get("role_keywords", [r"project\s+manager"])) + ")", re.I)
BAD = re.compile("(" + "|".join(CFG.get("stop_keywords", [r"курьер"])) + ")", re.I)

# Реклама обучения: каналы про профессию наполовину торгуют курсами.
ADS = re.compile(
    r"(вебинар|марафон|интенсив|мастер-класс|курс\w*\s+(?:по|для)|тренажер|тренажёр|"
    r"первый урок|записаться|регистрация\s+по\s+ссылке|промокод|скидк\w+|"
    r"бесплатн\w+\s+урок|обучени\w+\s+профессии)", re.I)

SALARY = re.compile(
    r"(?:от\s*)?\d[\d\s  ]{2,}(?:\s*[-–—]\s*\d[\d\s  ]{2,})?\s*"
    r"(?:₸|тенге|тг|₽|руб|р\.|\$|USD|KZT|RUB)", re.I)
CONTACT = re.compile(r"(?<![A-Za-z0-9._%+-])@[A-Za-z][A-Za-z0-9_]{3,31}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)


def fetch(channel):
    """curl, а не WebFetch: WebFetch тащит всю страницу в контекст."""
    r = subprocess.run(
        ["curl", "-sSL", "--max-time", "25", "-A", "Mozilla/5.0",
         f"https://t.me/s/{channel}"],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl вернул {r.returncode}: {r.stderr[:200]}")
    return r.stdout


def strip_tags(html):
    html = re.sub(r"<br\s*/?>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = htmlmod.unescape(html)
    return re.sub(r"[^\S\n]+", " ", html).strip()


def parse(html, channel):
    """Достаём посты: id, дата, текст. Порядок на странице — от старых к новым."""
    posts = []
    chunks = html.split('class="tgme_widget_message ')
    for chunk in chunks[1:]:
        m = re.search(r'data-post="%s/(\d+)"' % re.escape(channel), chunk)
        if not m:
            continue
        pid = int(m.group(1))
        tm = re.search(r'<time datetime="([^"]+)"', chunk)
        when = tm.group(1)[:10] if tm else "?"
        bm = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*'
            r'<div class="tgme_widget_message_(?:footer|info)', chunk, re.S)
        if not bm:
            bm = re.search(
                r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*)', chunk, re.S)
        text = strip_tags(bm.group(1)) if bm else ""
        posts.append({"id": pid, "date": when, "text": text})
    return posts


def interesting(text, take_all):
    if BAD.search(text) or ADS.search(text):
        return False
    return True if take_all else bool(GOOD.search(text))


def snippet(text, width=190):
    """Фрагмент вокруг совпадения с ролью — чтобы было видно, за что пост взят.
    Начало поста для этого не годится: совпадение часто ниже по тексту."""
    flat = re.sub(r"\s+", " ", text).strip()
    m = GOOD.search(flat)
    if not m:
        return flat[:width]
    start = max(0, m.start() - width // 3)
    out = flat[start:start + width]
    return ("…" if start else "") + out


def brief(post, channel):
    text = post["text"]
    sal = SALARY.search(text)
    contacts = [c for c in CONTACT.findall(text)
                if c.lower() != "@" + channel.lower()][:2]
    mails = EMAIL.findall(text)[:1]
    head = snippet(text)
    return {
        "url": f"https://t.me/{channel}/{post['id']}",
        "date": post["date"],
        "salary": sal.group(0).strip() if sal else "—",
        "contact": ", ".join(contacts + mails) or "—",
        "head": head,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", help="ключ из telegram_channels в config/search.json")
    ap.add_argument("--all", action="store_true",
                    help="не фильтровать по ключевым словам роли")
    ap.add_argument("--dry-run", action="store_true", help="не запоминать позиции")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--reset", metavar="КАНАЛ")
    args = ap.parse_args()

    state = load_state()

    if args.list:
        for reg, chans in CHANNELS.items():
            print(f"[{reg}]")
            for c in chans:
                print(f"  {c:24} последний виденный id: {state.get(c, '—')}")
        return

    if args.reset:
        state.pop(args.reset, None)
        save_state(state)
        print(f"позиция {args.reset} сброшена, следующий проход прочитает ленту целиком")
        return

    if not args.region:
        raise SystemExit("нужен --region <имя> (или --list)")

    total_new = total_hits = 0
    fails = []
    for channel in CHANNELS.get(args.region, []):
        try:
            html = fetch(channel)
            posts = parse(html, channel)
        except Exception as e:
            fails.append(f"{channel}: {e}")
            continue
        if not posts:
            fails.append(f"{channel}: постов не разобрано (изменилась вёрстка?)")
            continue

        last = state.get(channel, 0)
        fresh = [p for p in posts if p["id"] > last]
        top = max(p["id"] for p in posts)
        total_new += len(fresh)

        hits = [brief(p, channel) for p in fresh if interesting(p["text"], args.all)]
        total_hits += len(hits)

        if not fresh:
            print(f"\n### @{channel} — новых постов нет (стоит на id {top})")
        else:
            print(f"\n### @{channel} — новых {len(fresh)}, подходящих {len(hits)}")
            for h in hits:
                print(f"  {h['date']}  {h['salary']}  {h['contact']}")
                print(f"    {h['head']}")
                print(f"    {h['url']}")

        if not args.dry_run:
            state[channel] = top

    if not args.dry_run:
        save_state(state)

    print(f"\nИТОГО: новых постов {total_new}, подходящих {total_hits}")
    if fails:
        print("НЕ ОТРАБОТАЛИ: " + "; ".join(fails))
    if args.dry_run:
        print("(dry-run: позиции не сохранены)")


if __name__ == "__main__":
    main()
