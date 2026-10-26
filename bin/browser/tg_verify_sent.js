/* tg_verify_sent.js — ШАГ 4: доказательство доставки. Проверено вживую.
 *
 * Единственное доказательство отправки — наши пузыри в открытом чате: последний
 * исходящий текст начинается как наш текст, и среди исходящих есть PDF с нужным именем.
 * Ни клик, ни исчезновение окна доказательством не являются.
 * Запускать через 3–5 с после отправки файла, в том же чате (сверить tg_peer_check.js).
 */
const out = [...document.querySelectorAll('.chat.active .bubble.is-out')].slice(-4);
const docs = out.map(b => (b.querySelector('.document-name') || {}).innerText).filter(Boolean);
const texts = out.map(b => (b.querySelector('.message') || {}).innerText || '').filter(t => t && !/\.pdf/i.test(t.slice(0, 80)));
({ outgoing: document.querySelectorAll('.chat.active .bubble.is-out').length,
   lastText: (texts[texts.length - 1] || '').slice(0, 80), docs,
   pending: document.querySelectorAll('.chat.active .bubble.is-out .time-sending, .chat.active .bubble.is-sending').length })
