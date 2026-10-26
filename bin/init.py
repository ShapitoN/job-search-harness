#!/usr/bin/env python3
"""Первичная настройка: создаёт data/ и config/search.json из шаблонов. Ничего не перезаписывает.

    python3 bin/init.py
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COPY = [
    ("config/search.example.json", "config/search.json"),
    ("core/candidate.template.md", "data/candidate.md"),
    ("templates/resume-base.template.md", "data/resume/base.md"),
    ("templates/blacklist.template.txt", "data/blacklist.txt"),
    ("templates/STATE.template.md", "STATE.md"),
]
for src, dst in COPY:
    s, d = os.path.join(ROOT, src), os.path.join(ROOT, dst)
    if os.path.exists(d):
        print(f"оставил как есть: {dst}")
        continue
    os.makedirs(os.path.dirname(d), exist_ok=True)
    shutil.copy(s, d)
    print(f"создал: {dst}")
for d in ("data/log", "data/resume/adapted", "data/main"):
    os.makedirs(os.path.join(ROOT, d), exist_ok=True)
print("\nДальше: заполните data/candidate.md, data/resume/base.md и config/search.json (docs/SETUP.md).")
