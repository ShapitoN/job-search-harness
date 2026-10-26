#!/usr/bin/env python3
"""Собрать PDF резюме из Markdown — для версий, подогнанных под вакансию.

    python3 bin/resume_pdf.py data/resume/adapted/2026-01-15-acme.md
    → data/resume/adapted/2026-01-15-acme.pdf

Markdown → HTML (библиотека markdown) → PDF через Chrome без окна, с отдельным
временным профилем, чтобы не задевать ваш рабочий Chrome. Оформление — спокойное,
под печать A4, без цвета кроме одного тёмно-синего для заголовков.

Печатает путь к PDF и его размер. Код возврата не 0 — PDF не собран, и
отправлять подогнанную версию нельзя: письмо уходит со стандартным резюме.
"""

import html
import pathlib
import shutil
import subprocess
import sys
import tempfile

import markdown

CSS = """
@page { size: A4; margin: 16mm 16mm 16mm 16mm; }
body { font-family: "Ubuntu Sans", "Ubuntu", "DejaVu Sans", Arial, sans-serif;
       font-size: 10.5pt; line-height: 1.45; color: #1d1f23; }
h1 { font-size: 19pt; margin: 0 0 2pt 0; color: #1f3550; }
h1 + p { margin-top: 0; color: #4a4d55; }
h2 { font-size: 12pt; margin: 14pt 0 4pt 0; padding-bottom: 2pt;
     border-bottom: 1px solid #c9ccd3; color: #1f3550; text-transform: uppercase;
     letter-spacing: .04em; }
h3 { font-size: 11pt; margin: 9pt 0 2pt 0; }
p { margin: 3pt 0; }
ul { margin: 3pt 0 3pt 0; padding-left: 15pt; }
li { margin: 1.5pt 0; }
strong { color: #111; }
a { color: #1f3550; text-decoration: none; }
"""


def find_chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def main():
    if len(sys.argv) != 2 or not sys.argv[1].endswith(".md"):
        print("использование: resume_pdf.py <файл.md>", file=sys.stderr)
        return 2
    src = pathlib.Path(sys.argv[1]).resolve()
    if not src.exists():
        print(f"нет файла: {src}", file=sys.stderr)
        return 2
    text = src.read_text(encoding="utf-8")
    if "<<" in text or "TODO" in text or "{{" in text:
        print("ОТКАЗ: в тексте остались маркеры-заглушки (<<, TODO, {{)", file=sys.stderr)
        return 3
    body = markdown.markdown(text, extensions=["extra", "sane_lists"])
    title = html.escape(src.stem)
    page = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f"<title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>")

    chrome = find_chrome()
    if not chrome:
        print("ОТКАЗ: не найден Chrome/Chromium для печати в PDF", file=sys.stderr)
        return 4
    out = src.with_suffix(".pdf")
    with tempfile.TemporaryDirectory(prefix="resume-pdf-") as tmp:
        page_file = pathlib.Path(tmp) / "resume.html"
        page_file.write_text(page, encoding="utf-8")
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
               f"--user-data-dir={tmp}/profile", "--no-pdf-header-footer",
               f"--print-to-pdf={out}", page_file.as_uri()]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if res.returncode != 0 or not out.exists() or out.stat().st_size < 5000:
        print("ОТКАЗ: Chrome не собрал PDF\n" + res.stderr[-800:], file=sys.stderr)
        return 5
    print(f"{out}  {out.stat().st_size // 1024} КБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
