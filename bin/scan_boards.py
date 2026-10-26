#!/usr/bin/env python3
"""
scan_boards.py — разведка hh одним вызовом, без участия модели.

Зачем: ходить по поисковым выдачам моделью дорого. Механическую часть (сходить по
запросам, собрать карточки, выкинуть виденное и то, что ниже порога) делает скрипт.
Агенту остаётся оценить готовую таблицу на десяток строк.

Как: hh отдаёт всю выдачу готовым JSON в <template id="HH-Lux-InitialState">.
Разбираем его, а не разметку. Публичный api.hh.ru может отвечать 403 — не полагаться.

Настройка — config/search.json (из config/search.example.json), блок "boards":
  host          hh.ru / hh.kz / hh.by ...
  area          код региона hh (113 Россия, 40 Казахстан, 1 Москва, 2 Санкт-Петербург)
  roles         коды профессиональных ролей hh (107 руководитель проектов, 73 менеджер
                продукта, 148 системный аналитик, 96 программист...). Справочник:
                https://api.hh.ru/professional_roles
  min_salary    порог по деньгам в валюте региона (вилки ниже — отсев)
  currency      RUR / KZT / USD ...
  exclude_titles  регулярное выражение для названий, которые отсеиваем
  exclude_companies  регулярное выражение для компаний, которым не пишем

Дедуп: ссылки, уже записанные в data/<регион>/seen-boards.txt, не показываются.
Файл дописывается только при --remember.

Использование:
  scan_boards.py --region main                 # обойти запросы
  scan_boards.py --region main --remember      # и записать ссылки в seen-boards
  scan_boards.py --region main --min 150000    # свой порог
  scan_boards.py --region main --with-seen     # показать и уже виденные
"""

import argparse
import html as htmlmod
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("JOBSEARCH_DATA", os.path.join(ROOT, "data"))
CONFIG_PATH = os.environ.get("JOBSEARCH_CONFIG", os.path.join(ROOT, "config", "search.json"))

# Курсы нужны только чтобы сравнить вилку с порогом: подправьте под себя.
TO_RUB = {"RUR": 1.0, "KZT": 0.18, "USD": 90.0, "EUR": 100.0, "BYR": 28.0, "UAH": 2.2}
TO_KZT = {k: v / 0.18 for k, v in TO_RUB.items()}


def load_regions():
    if not os.path.exists(CONFIG_PATH):
        raise SystemExit(f"нет {CONFIG_PATH} — скопируйте config/search.example.json и заполните")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        boards = json.load(f).get("boards", {})
    for name, r in boards.items():
        r["seen"] = os.path.join(DATA, name, "seen-boards.txt")
    return boards


REGIONS = load_regions()
_first = next(iter(REGIONS.values()), {})
ROLES = _first.get("roles", [])


def _rx(key):
    pat = _first.get(key)
    return re.compile(pat, re.I) if pat else re.compile(r"(?!x)x")


NOT_IT = _rx("exclude_titles")
CLOSED = _rx("exclude_companies")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def fetch(url):
    r = subprocess.run(["curl", "-sSL", "--max-time", "30", "-A", UA, url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl {r.returncode}: {r.stderr[:150]}")
    return r.stdout


def extract(page):
    m = re.search(r'<template[^>]*id="HH-Lux-InitialState"[^>]*>(.*?)</template>',
                  page, re.S)
    if not m:
        raise RuntimeError("не нашёл HH-Lux-InitialState (вёрстка изменилась?)")
    data = json.loads(htmlmod.unescape(m.group(1)))
    return data.get("vacancySearchResult", {}).get("vacancies", []) or []


def money(comp, region):
    """Вернуть (строка для человека, сумма в валюте региона или None)."""
    if not comp or "noCompensation" in comp:
        return "не указана", None
    lo, hi = comp.get("from"), comp.get("to")
    cur = comp.get("currencyCode") or comp.get("currency") or region["currency"]
    gross = comp.get("gross")
    parts = []
    if lo:
        parts.append(f"от {lo:,}".replace(",", " "))
    if hi:
        parts.append(f"до {hi:,}".replace(",", " "))
    if not parts:
        return "не указана", None
    label = " ".join(parts) + f" {cur}" + (" gross" if gross else "")
    table = TO_KZT if region["currency"] == "KZT" else TO_RUB
    rate = table.get(cur, 1.0)
    return label, (lo or hi) * rate


def load_seen(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8", errors="replace") as f:
        return set(re.findall(r"/vacancy/(\d+)", f.read()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, help="ключ из boards в config/search.json")
    ap.add_argument("--min", type=int, help="порог по деньгам, валюта региона")
    ap.add_argument("--remember", action="store_true",
                    help="дописать показанные ссылки в seen-boards.txt")
    ap.add_argument("--with-seen", action="store_true", help="не прятать виденные")
    ap.add_argument("--pages", type=int, default=1, help="страниц на запрос")
    args = ap.parse_args()

    if args.region not in REGIONS:
        raise SystemExit(f"нет региона {args.region} в {CONFIG_PATH}")
    region = REGIONS[args.region]
    global ROLES, NOT_IT, CLOSED
    ROLES = region.get("roles", [])
    NOT_IT = re.compile(region["exclude_titles"], re.I) if region.get("exclude_titles") else re.compile(r"(?!x)x")
    CLOSED = re.compile(region["exclude_companies"], re.I) if region.get("exclude_companies") else re.compile(r"(?!x)x")
    threshold = args.min if args.min is not None else region["min_salary"]
    seen = set() if args.with_seen else load_seen(region["seen"])

    found, low, noise, closed, fails = {}, 0, 0, 0, []
    for role in ROLES:
        for page in range(args.pages):
            q = urllib.parse.urlencode({
                "professional_role": role, "area": region["area"],
                "order_by": "publication_time", "items_on_page": "20", "page": page,
            })
            url = f"https://{region['host']}/search/vacancy?{q}"
            try:
                items = extract(fetch(url))
            except Exception as e:
                fails.append(f"роль {role} стр. {page}: {e}")
                continue
            for v in items:
                vid = str(v.get("vacancyId") or "")
                if not vid or vid in found or vid in seen:
                    continue
                label, amount = money(v.get("compensation"), region)
                if amount is not None and amount < threshold:
                    low += 1
                    continue
                name = (v.get("name") or "").strip()
                company = ((v.get("company") or {}).get("visibleName")
                           or (v.get("company") or {}).get("name") or "—")
                if NOT_IT.search(name):
                    noise += 1
                    continue
                if CLOSED.search(company):
                    closed += 1
                    continue
                found[vid] = {
                    "id": vid,
                    "name": name,
                    "company": company,
                    "area": ((v.get("area") or {}).get("name") or "—"),
                    "salary": label,
                    "date": ((v.get("publicationTime") or {}).get("$") or "")[:10],
                    "url": ((v.get("links") or {}).get("desktop")
                            or f"https://{region['host']}/vacancy/{vid}"),
                }
            time.sleep(1)   # не долбить площадку

    rows = sorted(found.values(), key=lambda r: r["date"], reverse=True)
    for r in rows:
        print(f"{r['date']}  {r['company']} — {r['name']}")
        print(f"    {r['salary']} · {r['area']} · {r['url']}")

    print(f"\nИТОГО: новых {len(rows)}, отсеяно по деньгам {low}, "
          f"не-IT ролей {noise}, закрытых компаний {closed}, "
          f"скрыто как виденное {'выключено' if args.with_seen else len(seen)}")
    if fails:
        print("НЕ ОТРАБОТАЛИ: " + "; ".join(fails))

    if args.remember and rows:
        os.makedirs(os.path.dirname(region["seen"]), exist_ok=True)
        with open(region["seen"], "a", encoding="utf-8") as f:
            for r in rows:
                f.write(f"{r['url']}  # {r['company']} — {r['name']} ({r['date']})\n")
        print(f"записано в {region['seen']}: {len(rows)} ссылок")


if __name__ == "__main__":
    main()
