/* hh_chats_awaiting.js — читает список чатов hh и возвращает те, где ждут ответа пользователя.
 *
 * Запускать через javascript_exec на вкладке https://hh.ru/chat (нужна живая сессия пользователя:
 * у hh нет публичного API для переписки, а с серверного IP и api, и страницы отдают 403/302).
 *
 * ВАЖНО про исполнение: этот файл — тело top-level await скрипта, БЕЗ обёртки в async IIFE.
 * Через javascript_exec `(async () => {...})()` возвращает голый Promise, который сериализуется
 * в "{}" — резолвленное значение теряется. Вставлять содержимое файла в exec как есть,
 * последним выражением должен остаться объектный литерал в скобках.
 *
 * ВАЖНО про DOM: список чатов виртуализирован (virtualized-list) — в DOM единовременно лежат
 * только видимые ~13 строк из десятков/сотен. Скрипт сам докручивает контейнер до конца,
 * иначе большая часть чатов останется невидимой и результат будет ложно-пустым.
 *
 * Разбор идёт ВНУТРИ страницы, наружу уходит только компактный JSON — это и есть вся экономия.
 * Никогда не возвращать innerText целиком: страница чатов весит десятки килобайт.
 *
 * Возвращает: { ok, authed, total, awaiting: [{chatId, url, company, vacancy, lastFrom, preview, waiting}] }
 * DOM hh меняется без предупреждения, поэтому селекторы завязаны на data-qa, а при полном
 * промахе возвращается ok:false с диагностикой — молча пустой список опаснее.
 *
 * Проверено вживую. на hh.ru/chat (после входа пользователя).
 */

if (/account\/login/.test(location.href)) {
  ({ ok: false, authed: false, total: 0, awaiting: [], note: "не авторизован: редирект на страницу входа" });
} else {

const ANCHOR_SEL = 'a[data-qa^="chatik-open-chat-"]';

const scroller = document.querySelector('[class*="chats--"]');
const collected = new Map();

const harvest = () => {
  const anchors = Array.from(document.querySelectorAll(ANCHOR_SEL));
  for (const a of anchors) {
    const id = (a.getAttribute('data-qa') || '').replace('chatik-open-chat-', '');
    if (collected.has(id)) continue;

    const get = (qa) => {
      const el = a.querySelector(`[data-qa="${qa}"]`);
      return el ? (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ') : '';
    };

    const vacancy = get('chat-cell-title');
    const company = get('chat-cell-subtitle');
    const time = get('chat-cell-creation-time');
    const badge = get('chatik-info-badges');
    // Галочка статуса появляется только у СВОЕГО последнего отправленного сообщения —
    // надёжный признак того, что мяч уже на стороне работодателя.
    // Статусов два: "доставлено" и "прочитано". фильтр ловил только первый,
    // из-за чего чат (собственное сообщение пользователя, уже прочитанное)
    // попал в awaiting как ждущий ответа. Проверять надо оба.
    const deliveredByMe = !!a.querySelector(
      '[data-qa="status-icon-delivered"], [data-qa="status-icon-read"], ' +
      '[class*="chat-bubble-icon-delivered"], [class*="chat-bubble-icon-read"]'
    );

    const raw = (a.innerText || '').trim();
    const lines = raw.split('\n').map(s => s.trim()).filter(Boolean);
    // hh вставляет типографские NBSP ( ) внутри превью ("и опыт", "с вами" и т.п.) —
    // без нормализации литеральные пробелы в CLOSED_PREVIEW/ECHO_PREVIEW/AUTOREPLY_PREVIEW
    // не совпадают, и автосообщения утекают в awaiting. Проверено вживую.,
    // повторный проход: RichBee/Ёбидоёби/Первый Бит с автосообщением не отфильтровались.
    const preview = lines
      .filter(l => l !== vacancy && l !== time && l !== company && l !== badge)
      .join(' ')
      .replace(/\u00A0/g, ' ')
      .slice(0, 250);

    collected.set(id, {
      chatId: id,
      url: new URL(a.getAttribute('href'), location.origin).href,
      company, vacancy, time, deliveredByMe, badge, preview
    });
  }
};

harvest();
if (scroller) {
  let lastTop = -1;
  for (let i = 0; i < 60; i++) {
    scroller.scrollTop = scroller.scrollTop + 350;
    await new Promise(r => setTimeout(r, 130));
    harvest();
    if (scroller.scrollTop === lastTop) break;
    lastTop = scroller.scrollTop;
    if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 5) break;
  }
}

const all = Array.from(collected.values());

// "Отказ" — терминальный статус, отвечать некуда и незачем, даже если формально непрочитан.
// "Отклик на вакансию" — это эхо самой заявки, диалога ещё не было, отвечать не на что.
// ВАЖНО: \b в JS-регулярках не видит кириллицу как \w (только [A-Za-z0-9_]), поэтому
// /^Отказ\b/ никогда не совпадает с кириллическим "Отказ" — проверено вживую,
// список awaiting был забит закрытыми чатами. Без \b, привязка к концу строки — потому что
// иногда в preview перед "Отказ" остаётся дублирующийся заголовок вакансии.
const CLOSED_PREVIEW = /(^|\s)Отказ$/i;
const ECHO_PREVIEW = /^Отклик на вакансию$/i;
// Стандартное автосообщение hh сразу после отклика ("мы свяжемся с вами, если подойдёте") —
// не вопрос и не запрос действия, мяч остаётся на работодателе. Отличается от ECHO_PREVIEW
// тем, что это не пустое эхо отклика, а первый (иногда единственный) месседж в чате.
const AUTOREPLY_PREVIEW = /Рассмотрим ваше резюме\.\s*Если навыки и опыт подойдут/i;
// Второй вариант автоответа hh, замечен —
// тоже подтверждение получения отклика сразу после отправки, а не сообщение от человека.
const AUTOREPLY_PREVIEW2 = /Благодарим вас за отклик на вакансию.*Наша команда внимательно изучит ваше резюме/i;
// Третий вариант — подтверждение hh-бота ПОСЛЕ прохождения скрининговых вопросов
// (не сразу после отклика, а после диалога с ботом). Замечен сразу в трёх
// чатах на hh.ru (Фрифлекс, Gravity Field, Edplace): "Ваши ответы отправлены работодателю",
// "Все ваши ответы я записал", "Всё зафиксировал... Передаю информацию работодателю".
// Без checkmark deliveredByMe (сообщение не от пользователя), но это тоже не человек — это бот,
// подтверждающий, что данные уже переданы. Мяч на работодателе, а не на пользователе.
const AUTOREPLY_PREVIEW3 = /Ваши ответы отправлены работодателю|Все ваши ответы я записал|Всё зафиксировал.*Передаю информацию работодателю/i;

const awaiting = all
  .filter(c => !c.deliveredByMe)          // последним писал не пользователь
  .filter(c => !CLOSED_PREVIEW.test(c.preview))
  .filter(c => !ECHO_PREVIEW.test(c.preview))
  .filter(c => !AUTOREPLY_PREVIEW2.test(c.preview))
  .filter(c => !AUTOREPLY_PREVIEW.test(c.preview))
  .filter(c => !AUTOREPLY_PREVIEW3.test(c.preview))
  .map(c => ({
    chatId: c.chatId,
    url: c.url,
    company: c.company,
    vacancy: c.vacancy,
    lastFrom: 'работодатель',
    preview: c.preview.slice(0, 200),
    time: c.time
  }));

({ ok: true, authed: true, total: all.length, awaiting, note: `собрано ${all.length} чатов после докрутки списка` });
}
