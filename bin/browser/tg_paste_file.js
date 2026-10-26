/* tg_paste_file.js — ШАГ 3: прикрепить PDF резюме. Проверено вживую.
 *
 * Проблема, висевшая с 23.09: кнопка-скрепка открывает системный диалог выбора файла,
 * до которого агент не дотягивается. Рабочий путь в два хода:
 *   а) find «file input in message composer» → ref; file_upload(ref, [путь к PDF]).
 *      Сам по себе этот ход НИЧЕГО не показывает — Telegram его не слушает.
 *   б) этот файл: берёт PDF из того input и вставляет его как Ctrl+V.
 *      Открывается окно «Send File» с именем PDF.
 * Затем отправка: computer key "Enter" (или клик по синей кнопке окна).
 *
 * ⚠️ Поле ввода перед этим шагом должно быть ПУСТЫМ (текст уже отправлен) —
 * иначе Telegram заберёт его в подпись к файлу.
 */
const inp = document.querySelector('.chat.active input[type=file]') || document.querySelector('.new-message-wrapper input[type=file]');
const f = inp && inp.files && inp.files[0];
if (!f) { ({ ok: false, err: 'в input нет файла — сначала file_upload' }) }
else {
  const dt = new DataTransfer(); dt.items.add(f);
  const ed = document.querySelector('.chat.active .input-message-input[contenteditable=true]');
  ed.focus();
  ed.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
  await new Promise(r => setTimeout(r, 1500));
  const pop = document.querySelector('.popup-send-photo, .popup-new-media');
  const txt = pop ? pop.innerText : '';
  ({ ok: !!pop && txt.includes(f.name), file: f.name, size: f.size,
     captionEmpty: /Add a caption|Добавить подпись/i.test(txt) })
}
