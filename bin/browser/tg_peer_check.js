/* tg_peer_check.js — ШАГ 1 отправки в Telegram Web: какой чат ДЕЙСТВИТЕЛЬНО открыт.
 *
 * Проверено вживую. на web.telegram.org/k/.
 *
 * ⚠️ Смена адреса НЕ переключает чат. navigate на https://web.telegram.org/k/#@username,
 * когда вкладка уже на web.telegram.org, меняет строку адреса, а открытым остаётся
 * ПРЕЖНИЙ чат (30.09: адрес #@telegram, открыто «Избранное»). Так 23.09 текст едва
 * не ушёл не тому человеку. Поэтому открывать чат ТОЛЬКО с полной перезагрузкой:
 *   javascript_exec: location.href='https://web.telegram.org/k/#@username'; location.reload(); 1
 *   затем подождать 10–15 с (страница грузится с нуля) и запустить этот файл.
 *
 * Возвращает @username открытого чата из внутреннего состояния Telegram Web, а не
 * из заголовка (в заголовке — отображаемое имя, его можно спутать).
 * Отправлять можно ТОЛЬКО если username совпал с целью без учёта регистра
 * и outgoing == 0 (нашего сообщения в диалоге ещё нет — значит, это первое).
 *
 * Как исполнять: содержимое файла целиком в javascript_exec, без обёртки.
 */
// после перезагрузки страница поднимается 15–25 с — ждём сами, до 30 с (javascript_exec рвётся на 45 с — не больше)
for (let i = 0; i < 30 && !(window.appImManager?.chat?.peerId && document.querySelector('.chat.active')); i++)
  await new Promise(r => setTimeout(r, 1000));
await new Promise(r => setTimeout(r, 1500));   // дать догрузиться истории
const im = window.appImManager;
const r = { hash: location.hash };
try {
  const pid = im.chat.peerId;
  r.peerId = pid;
  const p = pid > 0
    ? await im.managers.appUsersManager.getUser(pid)
    : await im.managers.appChatsManager.getChat(-pid);
  r.username = p.username || (p.usernames || []).map(u => u.username).join(',');
  r.name = p.first_name ? `${p.first_name} ${p.last_name || ''}`.trim() : p.title;
  r.isUser = pid > 0;
} catch (e) { r.err = String(e).slice(0, 200); }
const chat = document.querySelector('.chat.active');
r.outgoing = chat ? chat.querySelectorAll('.bubble.is-out').length : null;
r.canWrite = !!(chat && chat.querySelector('.input-message-input[contenteditable=true]'));
r
