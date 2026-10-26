#!/usr/bin/env python3
"""Журнал компаний: кому писали, когда, каким каналом. Один CSV, одна команда на действие.

Зачем скриптом, а не руками модели: журнал растёт до сотен строк, и вычитывать его в
контекст — самая дешёвая по смыслу и самая дорогая по токенам работа. Агент задаёт
вопрос («писали ли мы Acme за 30 дней?») и получает одну строку ответа.

Файл: data/ledger.csv (создаётся сам). Колонки:
  company, domain, region, channel, status, date, contact, url, note

status:
  found      нашли на доске/в канале, ещё не писали
  sent       отправлено (письмо / отклик / сообщение в Telegram)
  replied    ответили нам
  bounced    не дошло (письмо отскочило) — компания НЕ затронута, окно не расходуется
  rejected   отказ
  blocked    чёрный список, не писать никогда

Окно дубля — 30 дней по факту отправки (status sent/replied/rejected). Присутствие
в журнале касанием НЕ считается: большинство строк — находки, которым ещё не писали.

Команды:
  ledger.py find "Acme"                       есть ли компания (по названию и домену)
  ledger.py touched --days 30                 кому писали за N дней (только отправленное)
  ledger.py add "Acme" --domain acme.com --region main --url https://hh.ru/vacancy/1
  ledger.py mark-sent "Acme" --channel email --contact hr@acme.com [--date 2026-01-15]
  ledger.py set-status "Acme" bounced --note "адрес hr@ мёртв"
  ledger.py stats [--today]                   счётчики по строкам, всегда пересчитываются
  ledger.py blocked "Acme"                    в чёрном списке?  (код возврата 1, если да)
"""
import argparse
import csv
import datetime as dt
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("JOBSEARCH_DATA", os.path.join(ROOT, "data"))
LEDGER = os.path.join(DATA, "ledger.csv")
COLS = ["company", "domain", "region", "channel", "status", "date", "contact", "url", "note"]
CONTACTED = {"sent", "replied", "rejected"}


def norm(name):
    """Название для сравнения: без регистра, кавычек, юрформы и пробелов.
    Похожие названия — РАЗНЫЕ компании, молча не склеиваем: см. cmd_find."""
    n = re.sub(r"[\"'«»().,]", " ", name.lower())
    n = re.sub(r"\b(ооо|ао|зао|пао|ип|llc|ltd|inc|gmbh|тоо)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def load():
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save(rows):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, LEDGER)


def match(rows, name):
    key = norm(name)
    dom = name.lower()
    return [r for r in rows if norm(r["company"]) == key or (r["domain"] and r["domain"].lower() == dom)]


def similar(rows, name):
    key = norm(name)
    out = []
    for r in rows:
        other = norm(r["company"])
        if other != key and (key in other or other in key) and min(len(key), len(other)) >= 4:
            out.append(r)
    return out


def fmt(r):
    return (f"{r['company']} | {r['status']} | {r['date'] or '—'} | {r['channel'] or '—'} | "
            f"{r['contact'] or '—'} | {r['note']}")


def cmd_find(a):
    rows = load()
    hit = match(rows, a.name)
    for r in hit:
        print(fmt(r))
    if not hit:
        print(f"нет в журнале: {a.name}")
    sim = similar(rows, a.name)
    if sim:
        print("ПОХОЖИЕ (возможно, другая компания — не склеивать молча, решает человек):")
        for r in sim:
            print("  " + fmt(r))


def cmd_touched(a):
    since = dt.date.today() - dt.timedelta(days=a.days)
    n = 0
    for r in load():
        if r["status"] in CONTACTED and r["date"] and dt.date.fromisoformat(r["date"]) >= since:
            print(fmt(r))
            n += 1
    print(f"— {n} за {a.days} дн.")


def cmd_add(a):
    rows = load()
    if match(rows, a.name) or (a.domain and match(rows, a.domain)):
        print(f"уже есть: {a.name}")
        return
    rows.append({"company": a.name, "domain": a.domain or "", "region": a.region or "",
                 "channel": "", "status": "found", "date": "", "contact": "",
                 "url": a.url or "", "note": a.note or ""})
    save(rows)
    print(f"добавлено: {a.name}")


def cmd_mark_sent(a):
    rows = load()
    hit = match(rows, a.name)
    if not hit:
        sys.exit(f"ОТКАЗ: компании {a.name} нет в журнале — сначала `add`")
    r = hit[0]
    date = a.date or dt.date.today().isoformat()
    if r["status"] in CONTACTED and r["date"] == date and r["channel"] == a.channel:
        sys.exit(f"ОТКАЗ: {a.name} уже отмечена как отправленная {date} через {a.channel}")
    r.update(status="sent", date=date, channel=a.channel, contact=a.contact or r["contact"])
    save(rows)
    print(f"отмечено: {a.name} | {a.channel} | {date}")


def cmd_set_status(a):
    rows = load()
    hit = match(rows, a.name)
    if not hit:
        sys.exit(f"ОТКАЗ: компании {a.name} нет в журнале")
    for r in hit:
        r["status"] = a.status
        if a.note:
            r["note"] = a.note
        if a.status == "bounced":
            r["date"] = ""        # окно 30 дней не началось
    save(rows)
    print(f"{a.name}: статус {a.status}")


def cmd_stats(a):
    rows = load()
    today = dt.date.today().isoformat()
    if a.today:
        sent = [r for r in rows if r["status"] in CONTACTED and r["date"] == today]
        by = {}
        for r in sent:
            by[r["channel"] or "?"] = by.get(r["channel"] or "?", 0) + 1
        print(f"сегодня действий: {len(sent)} | " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
        return
    by = {}
    for r in rows:
        by[r["status"]] = by.get(r["status"], 0) + 1
    print(f"строк: {len(rows)} | " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))


def cmd_blocked(a):
    hit = [r for r in match(load(), a.name) if r["status"] == "blocked"]
    if hit:
        print(f"ЧЁРНЫЙ СПИСОК: {a.name}")
        sys.exit(1)
    print("не в чёрном списке")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("find"); s.add_argument("name"); s.set_defaults(fn=cmd_find)
    s = sub.add_parser("touched"); s.add_argument("--days", type=int, default=30); s.set_defaults(fn=cmd_touched)
    s = sub.add_parser("add"); s.add_argument("name"); s.add_argument("--domain"); s.add_argument("--region")
    s.add_argument("--url"); s.add_argument("--note"); s.set_defaults(fn=cmd_add)
    s = sub.add_parser("mark-sent"); s.add_argument("name")
    s.add_argument("--channel", required=True, choices=["email", "hh", "telegram"])
    s.add_argument("--contact"); s.add_argument("--date"); s.set_defaults(fn=cmd_mark_sent)
    s = sub.add_parser("set-status"); s.add_argument("name")
    s.add_argument("status", choices=["found", "sent", "replied", "bounced", "rejected", "blocked"])
    s.add_argument("--note"); s.set_defaults(fn=cmd_set_status)
    s = sub.add_parser("stats"); s.add_argument("--today", action="store_true"); s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("blocked"); s.add_argument("name"); s.set_defaults(fn=cmd_blocked)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
