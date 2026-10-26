#!/usr/bin/env python3
"""
Отправщик писем через Gmail API.

ЗАЧЕМ ЭТО СУЩЕСТВУЕТ
Приложить PDF к письму через браузер или через MCP-коннектор дорого: файл кодируется
в base64 прямо в контексте модели, и одно письмо съедает десятки и сотни тысяч токенов.
Здесь вложения кодируются НА ДИСКЕ. В контекст агента попадает одна строка результата.

ПРОВЕРКИ ВСТРОЕНЫ В СКРИПТ, А НЕ ОПИСАНЫ В ПРОМПТЕ
  • маркер-заглушка в теле        — письмо с "[ПРИКРЕПИТЬ РЕЗЮМЕ]" не уходит
  • вложения на месте и не пусты  — письмо без резюме бессмысленно
  • домен получателя принимает почту (MX/A), null MX отсекается
  • дубль по папке «Отправленные» — по адресу и по домену (одна компания = одно касание)
  • подтверждение из API, а не из факта вызова: после отправки письмо перечитывается
Любая непройденная проверка = отказ отправлять. Отказ дешевле ошибки: письмо не отозвать.

КОМАНДЫ
  auth          одноразовая авторизация (нужен ваш клик в браузере)
  send          отправить письмо
  check         сколько писем уже ушло на адрес (проверка дубля)
  check-domain  проверить пачку адресов до рассылки
  quota         сколько отправлено за последние сутки

ПРИМЕР
  python3 bin/send_email.py send \
      --to hr@example.com \
      --subject "Project manager: внедрение CRM" \
      --body-file data/log/letter.txt \
      --attach data/resume/resume.pdf --require-attachments 1
"""

import argparse
import base64
import datetime as dt
import mimetypes
import os
import re
import sys
from email.message import EmailMessage

SCOPES = ["https://www.googleapis.com/auth/gmail.send",
          "https://www.googleapis.com/auth/gmail.readonly"]

CONF_DIR = os.path.expanduser("~/.config/job-search")
CRED_FILE = os.path.join(CONF_DIR, "credentials.json")   # вы кладёте сюда из Google Cloud (docs/SETUP.md)
TOKEN_FILE = os.path.join(CONF_DIR, "token.json")        # создаётся при `auth`

# Служебные заглушки, с которыми письмо отправлять нельзя.
MARKERS = ["[ПРИКРЕПИТЬ", "[TODO", "[ВСТАВИТЬ", "[УТОЧНИТЬ", "[ЗАПОЛНИТЬ",
           "{{", "XXX", "ЛОРЕМ", "lorem ipsum"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def die(msg):
    print(f"ОТКАЗ: {msg}", file=sys.stderr)
    sys.exit(2)


# Приложение в Google Cloud в режиме «Testing»: Google отзывает доступ через 7 дней
# после `auth`. Проще раз в неделю переавторизоваться, чем публиковать приложение,
# поэтому скрипт сам напоминает в Telegram (если настроен bin/notify.py).
AUTH_DATE_FILE = os.path.join(CONF_DIR, "auth-date")      # дата последнего `auth`
ALERT_FILE = os.path.join(CONF_DIR, "auth-alert-sent")    # дедуп: "<вид> <дата>"
TOKEN_LIFE_DAYS = 7
AUTH_CMD = f"python3 {os.path.abspath(__file__)} auth"


def alert_once(kind, text):
    """Сообщение вам в Telegram, не чаще раза в сутки на один вид."""
    stamp = f"{kind} {dt.date.today().isoformat()}"
    try:
        with open(ALERT_FILE) as fh:
            if fh.read().strip() == stamp:
                return
    except OSError:
        pass
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from notify import notify
        notify(text)
        with open(ALERT_FILE, "w") as fh:
            fh.write(stamp)
    except Exception as exc:  # напоминание не должно ронять отправку
        print(f"предупреждение: не отправил напоминание в Telegram: {exc}", file=sys.stderr)


def warn_if_expiring():
    """За сутки до истечения недельного токена — напомнить заранее."""
    try:
        with open(AUTH_DATE_FILE) as fh:
            issued = dt.date.fromisoformat(fh.read().strip())
    except (OSError, ValueError):
        return
    left = TOKEN_LIFE_DAYS - (dt.date.today() - issued).days
    if left <= 1:
        alert_once("expiring",
                   f"Доступ к почте для поиска работы истекает "
                   f"{'сегодня' if left <= 0 else 'завтра'}. "
                   f"Обнови в терминале, займёт минуту:\n{AUTH_CMD}")


def service():
    """Клиент Gmail API. Молча обновляет протухший токен."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google.auth.exceptions import RefreshError
    from googleapiclient.discovery import build

    if not os.path.exists(TOKEN_FILE):
        die(f"нет {TOKEN_FILE} — сначала выполните: python3 {sys.argv[0]} auth")
    warn_if_expiring()
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                alert_once("expired",
                           f"Доступ к почте для поиска работы истёк — письма "
                           f"не уходят. Обнови в терминале:\n{AUTH_CMD}")
                die(f"токен отозван или истёк — повторите: {AUTH_CMD}")
            with open(TOKEN_FILE, "w") as fh:
                fh.write(creds.to_json())
        else:
            die("токен недействителен — повторите: python3 send_email.py auth")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def cmd_auth(_):
    from google_auth_oauthlib.flow import InstalledAppFlow
    os.makedirs(CONF_DIR, exist_ok=True)
    if not os.path.exists(CRED_FILE):
        die(f"нет {CRED_FILE}\n"
            f"  Google Cloud Console → APIs & Services → Credentials →\n"
            f"  Create credentials → OAuth client ID → Desktop app →\n"
            f"  скачать JSON и положить сюда: {CRED_FILE}")
    flow = InstalledAppFlow.from_client_secrets_file(CRED_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, "w") as fh:
        fh.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)
    with open(AUTH_DATE_FILE, "w") as fh:
        fh.write(dt.date.today().isoformat())
    print(f"готово, токен сохранён: {TOKEN_FILE}")
    print(f"действует {TOKEN_LIFE_DAYS} дней, за сутки до конца придёт напоминание в Telegram")


def count_sent_to(svc, address):
    res = svc.users().messages().list(
        userId="me", q=f"in:sent to:{address}", maxResults=5).execute()
    return res.get("resultSizeEstimate", 0)


def count_sent_to_domain(svc, address):
    """Сколько писем уже ушло на ЛЮБОЙ адрес этого домена.

    Сверки точного адреса мало: hr@ и info@ одной компании — это одно касание,
    а не два. Поэтому считаем по домену."""
    domain = (address or "").rsplit("@", 1)[-1].strip().lower()
    if not domain or "." not in domain:
        return 0
    res = svc.users().messages().list(
        userId="me", q=f"in:sent to:@{domain}", maxResults=5).execute()
    return res.get("resultSizeEstimate", 0)


def cmd_check(args):
    print(f"{args.to}: писем в «Отправленных» — {count_sent_to(service(), args.to)}")


def cmd_quota(_):
    svc = service()
    res = svc.users().messages().list(
        userId="me", q="in:sent newer_than:1d", maxResults=100).execute()
    n = len(res.get("messages", []))
    print(f"отправлено за последние сутки: {n}")


def _dig(rtype, name):
    """Короткий ответ dig или None, если dig недоступен."""
    import subprocess as _sp
    try:
        return _sp.run(["dig", "+short", rtype, name],
                       capture_output=True, text=True, timeout=8).stdout.strip()
    except Exception:
        return None


def domain_accepts_mail(domain):
    """Может ли домен вообще принять письмо. Возвращает (ok, причина).

    Наличия MX-записи мало. Три класса поломки:

      1. Записей нет вовсе — домена не существует.
      2. **MX есть, но указывает на несуществующий хост.** Проверка «MX есть»
         пропустила бы письмо в пустоту, поэтому резолвим и сам хост из MX.
      3. Сервер есть и резолвится, но не принимает соединение. Это здесь НЕ
         проверяется намеренно: проба порта 25 занимает секунды, часто режется
         провайдером и даёт ложные отказы. Для неё есть `check-domain --probe`.
    """
    mx = _dig("MX", domain)
    if mx is None:
        return True, "dig недоступен, проверка пропущена"   # не блокируем отправку
    if mx == "":
        if _dig("A", domain) == "":
            return False, "нет ни MX, ни A"
        return True, "MX нет, но есть A — почта пойдёт на сам домен"

    hosts = []
    for line in mx.splitlines():
        parts = line.split()
        if len(parts) == 2:
            host = parts[1].rstrip(".")
            if host == "":
                # RFC 7505 «null MX»: запись вида `0 .` — домен прямо объявляет,
                # что почту не принимает вообще. Не опечатка и не поломка, а
                # намеренная настройка. Писать туда бесполезно.
                return False, "null MX (RFC 7505) — домен объявил, что почту не принимает"
            hosts.append((int(parts[0]), host))
    if not hosts:
        return False, f"MX-запись нечитаема: {mx!r}"

    dead = []
    for _, host in sorted(hosts):
        if _dig("A", host) or _dig("AAAA", host):
            return True, f"MX {host} резолвится"
        dead.append(host)
    return False, f"MX указывает на несуществующий хост: {', '.join(dead)}"


def probe_smtp(host, port=25, timeout=6):
    """Принимает ли сервер соединение. Только для `check-domain`, не для отправки."""
    import socket
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
        banner = s.recv(200).decode("utf-8", "replace").strip().splitlines()
        s.close()
        return True, (banner[0][:60] if banner else "соединение принято")
    except socket.timeout:
        return False, "timeout — сервер не отвечает"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def cmd_check_domain(args):
    """Досылочная проверка адресов пачкой: чтобы не тратить квоту на мёртвые домены.

    Одно письмо = единица суточной квоты, поэтому дешевле проверить пачку целиком
    перед рассылкой, чем узнать об отказе через двое суток.
    """
    addrs = list(args.addresses)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            addrs += [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]

    bad = 0
    for addr in addrs:
        domain = addr.rsplit("@", 1)[-1]
        ok, reason = domain_accepts_mail(domain)
        if not ok:
            bad += 1
            print(f"ОТКАЗ   {addr:38} {reason}")
            continue
        if not args.probe:
            print(f"ok      {addr:38} {reason}")
            continue
        mx = _dig("MX", domain) or ""
        hosts = sorted((int(p[0]), p[1].rstrip("."))
                       for p in (l.split() for l in mx.splitlines()) if len(p) == 2)
        host = hosts[0][1] if hosts else domain
        alive, info = probe_smtp(host)
        if alive:
            print(f"ok      {addr:38} {host} — {info}")
        else:
            bad += 1
            print(f"МОЛЧИТ  {addr:38} {host} — {info}")

    print(f"\nвсего {len(addrs)}, проблемных {bad}")
    if bad:
        sys.exit(1)


def cmd_send(args):
    # --- проверки до всякой сети -------------------------------------------
    if not EMAIL_RE.match(args.to):
        die(f"адрес не похож на почтовый: {args.to}")

    # Домен обязан принимать почту. Адреса из каталогов и «угаданные» адреса часто
    # ведут на мёртвые домены; такое письмо съедает суточную квоту и отбивается.
    domain = args.to.rsplit("@", 1)[1]
    if not args.skip_mx_check:
        ok, reason = domain_accepts_mail(domain)
        if not ok:
            die(f"домен {domain} не принимает почту: {reason}. "
                f"Адрес недействителен — не тратить на него квоту. "
                f"Уверен, что адрес рабочий, — повтори с --skip-mx-check.")

    if not os.path.exists(args.body_file):
        die(f"нет файла с телом письма: {args.body_file}")
    body = open(args.body_file, encoding="utf-8").read().strip()
    if len(body) < 200:
        die(f"тело письма подозрительно короткое ({len(body)} симв.) — похоже на обрывок")

    hits = [m for m in MARKERS if m.lower() in body.lower()]
    if hits:
        die(f"в теле остались служебные заглушки: {', '.join(hits)}. "
            f"Исправьте тело письма и повторите.")

    if len(args.attach) < args.require_attachments:
        die(f"вложений {len(args.attach)}, требуется {args.require_attachments} "
            f"(например: резюме + рекомендательное письмо)")
    for path in args.attach:
        if not os.path.exists(path):
            die(f"нет файла вложения: {path}")
        if os.path.getsize(path) < 1024:
            die(f"вложение подозрительно пустое: {path}")

    # Проверка вхолостую не ходит в сеть — её можно гонять без авторизации.
    svc = None if args.dry_run else service()

    # --- защита от дубля ----------------------------------------------------
    if svc:
        already = count_sent_to(svc, args.to)
        if already and not args.allow_duplicate:
            die(f"на {args.to} уже отправлено писем: {already}. "
                f"Если это осознанный повтор — флаг --allow-duplicate")
        # Тот же домен — та же компания, даже если ящик другой.
        same_domain = count_sent_to_domain(svc, args.to)
        if same_domain and not args.allow_duplicate:
            die(f"на домен {args.to.rsplit('@', 1)[-1]} уже отправлено писем: "
                f"{same_domain} (другой ящик той же компании). "
                f"Если это осознанный повтор — флаг --allow-duplicate")

    # --- сборка письма; base64 живёт на диске, не в контексте ---------------
    msg = EmailMessage()
    msg["To"] = args.to
    msg["Subject"] = args.subject
    if args.from_name:
        msg["From"] = args.from_name
    msg.set_content(body)

    for path in args.attach:
        ctype, encoding = mimetypes.guess_type(path)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(path, "rb") as fh:
            msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype,
                               filename=os.path.basename(path))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    if args.dry_run:
        print(f"ПРОГОН БЕЗ ОТПРАВКИ: {args.to} | {args.subject} | "
              f"вложений {len(args.attach)} | размер {len(msg.as_bytes())} Б")
        return

    sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()

    # --- подтверждение из API, а не из факта вызова -------------------------
    got = svc.users().messages().get(userId="me", id=sent["id"], format="minimal").execute()
    size = got.get("sizeEstimate", 0)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%H:%M UTC")
    print(f"ОТПРАВЛЕНО {args.to} | {stamp} | id={sent['id']} | {size} Б | "
          f"вложений {len(args.attach)}")


def main():
    p = argparse.ArgumentParser(description="Отправка писем через Gmail API")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth", help="одноразовая авторизация").set_defaults(fn=cmd_auth)
    sub.add_parser("quota", help="сколько отправлено за сутки").set_defaults(fn=cmd_quota)

    cd = sub.add_parser("check-domain",
                        help="проверить пачку адресов до рассылки: примет ли домен почту")
    cd.add_argument("addresses", nargs="*")
    cd.add_argument("--file", help="файл со списком адресов, по одному в строке")
    cd.add_argument("--probe", action="store_true",
                    help="ещё и постучаться на порт 25 (медленнее, возможны ложные отказы)")
    cd.set_defaults(fn=cmd_check_domain)

    c = sub.add_parser("check", help="проверить, писали ли уже на адрес")
    c.add_argument("--to", required=True)
    c.set_defaults(fn=cmd_check)

    s = sub.add_parser("send", help="отправить письмо")
    s.add_argument("--to", required=True)
    s.add_argument("--subject", required=True)
    s.add_argument("--body-file", required=True)
    s.add_argument("--skip-mx-check", action="store_true",
                   help="не проверять MX/A домена получателя")
    s.add_argument("--attach", action="append", default=[],
                   help="путь к вложению, можно повторять")
    s.add_argument("--require-attachments", type=int, default=1)
    s.add_argument("--from-name", help='например: "Имя Фамилия <адрес>"')
    s.add_argument("--allow-duplicate", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_send)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
