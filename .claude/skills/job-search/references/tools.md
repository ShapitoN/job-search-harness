# Инструменты (`bin/`) и кто чем пользуется

| Скрипт | Что делает | Кто |
|---|---|---|
| `scan_boards.py --region main [--remember]` | обходит выдачи hh, отсеивает виденное, ниже порога и не-ту роль; печатает таблицу | scout-boards |
| `scan_telegram.py --region main` | читает только новое в публичных каналах, вытаскивает контакты и вилки | scout-telegram |
| `ledger.py …` | журнал: find / touched / add / mark-sent / set-status / stats / blocked | все |
| `send_email.py send …` | отправка письма с вложениями через Gmail API, со всеми проверками | outreach, replier |
| `send_email.py check-domain …` | пачка адресов: примет ли домен почту | outreach |
| `resume_pdf.py <файл.md>` | Markdown → PDF через headless Chrome | resume-tailor |
| `notify.py [--key K] "текст"` | сообщение вам в Telegram с дедупом | inbox-watcher, оркестратор |
| `browser/*.js` | куски JS для страницы hh и Telegram Web | inbox-watcher, оркестратор |

## Если скрипт упал
- `send_email.py` отвечает `ОТКАЗ: нет token.json` — **отправки в этом прогоне нет.** Не искать
  обход через браузер или MCP: это вернёт старую цену. Собрать письма в `data/log/`, честно
  написать в отчёте, что нужна авторизация, и дать пользователю команду
  `python3 bin/send_email.py auth`.
- Токен Gmail в режиме «Testing» живёт 7 дней — раз в неделю `auth` заново (скрипт сам напомнит
  в Telegram, если настроен `notify.py`).
- `scan_*` вернули пусто/ошибку — записать в раздел «Источники» отчёта, перейти к следующему.
- `resume_pdf.py` вернул код не 0 — подогнанную версию не отдавать, шлётся стандартное резюме.
