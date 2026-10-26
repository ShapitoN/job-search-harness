/* tg_insert_text.js — ШАГ 2: вставить многострочный текст в поле ввода, НЕ отправляя.
 *
 * Проверено вживую. Печать через computer.type не годится: Enter в тексте
 * отправляет сообщение, и письмо рвётся на куски. Здесь переносы вставляются
 * как insertLineBreak — абзацы сохраняются, ничего не уходит.
 *
 * Перед запуском отдельным exec положить текст:
 *   window.__tgText = <JSON-строка текста>;     // json.dumps(text, ensure_ascii=False)
 * Потом — содержимое этого файла целиком.
 *
 * Отправка — ОТДЕЛЬНЫМ действием, после сверки tg_peer_check.js: computer key "Enter".
 * Лимит текстового сообщения 4096 символов; шаблон telegram-direct укладывается.
 * Текст НЕ класть в подпись к файлу: лимит подписи 1024, длинный текст не влезет.
 */
const ed = document.querySelector('.chat.active .input-message-input[contenteditable=true]');
if (!ed) { ({ ok: false, err: 'нет поля ввода — чат не открыт или писать нельзя' }) }
else {
  ed.focus();
  document.execCommand('selectAll'); document.execCommand('delete');   // стереть черновик
  const parts = String(window.__tgText || '').split('\n');
  parts.forEach((p, i) => {
    if (p) document.execCommand('insertText', false, p);
    if (i < parts.length - 1) document.execCommand('insertLineBreak');
  });
  const got = ed.innerText.replace(/\s+/g, ' ').trim();
  const want = String(window.__tgText || '').replace(/\s+/g, ' ').trim();
  ({ ok: got === want, len: want.length, head: got.slice(0, 60) })
}
