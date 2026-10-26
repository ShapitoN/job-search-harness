/* hh_vacancy_fields.js — добирает пять полей по вакансиям, не покидая страницу.
 *
 * Запускать через javascript_exec на любой вкладке hh с живой сессией.
 * Подставить список ссылок на вакансии в URLS.
 *
 * Ключевой приём: fetch идёт ИЗ браузера пользователя (IP и куки пользователя), поэтому hh отвечает
 * нормально — с серверного IP тот же запрос даёт 403. Разбор здесь же, наружу уходят
 * только пять полей на вакансию, а не HTML. Одна вакансия наружу ≈ 60-80 токенов.
 */
(async () => {
  const URLS = [/* СЮДА ссылки вида https://hh.ru/vacancy/136545640 */];

  const pick = (doc, sels) => {
    for (const s of sels) {
      const el = doc.querySelector(s);
      const t = el && (el.innerText || el.textContent || "").trim();
      if (t) return t.replace(/\s+/g, " ");
    }
    return "";
  };

  const results = [];
  for (const url of URLS) {
    try {
      const html = await fetch(url, { credentials: "include" }).then(r => r.text());
      const doc = new DOMParser().parseFromString(html, "text/html");

      const salary = pick(doc, [
        '[data-qa="vacancy-salary"]',
        '[data-qa*="salary-compensation"]',
        '[class*="compensation"]'
      ]) || "не указана";

      const address = pick(doc, ['[data-qa="vacancy-view-location"]', '[data-qa*="vacancy-view-raw-address"]']);
      const city = pick(doc, ['[data-qa="vacancy-view-location"]']) || address;

      // Формат работы: hh пишет его и в блоке условий, и в теле описания.
      const modeSrc = (pick(doc, ['[data-qa="vacancy-view-employment-mode"]']) + " " +
                       pick(doc, ['[data-qa="common-vacancy-work-format"]']) + " " +
                       (doc.body ? doc.body.innerText.slice(0, 4000) : "")).toLowerCase();
      let format = "не указан";
      if (/гибрид/.test(modeSrc)) format = "гибрид";
      else if (/удал[её]нн|remote|из дома/.test(modeSrc)) format = "удалёнка";
      else if (/на месте работодателя|офис/.test(modeSrc)) format = "офис";

      // Страна: по домену и городу. hh.kz и упоминания городов КЗ → Казахстан.
      let country = "Россия";
      if (/hh\.kz/.test(url) || /Алматы|Астана|Шымкент|Караганда|Казахстан/i.test(address + " " + city)) {
        country = "Казахстан";
      }

      const description = pick(doc, ['[data-qa="vacancy-description"]']);
      const about = description.split(/\s+/).slice(0, 50).join(" ");

      results.push({
        url,
        company: pick(doc, ['[data-qa="vacancy-company-name"]', '[data-qa*="company-name"]']),
        vacancy: pick(doc, ['[data-qa="vacancy-title"]', "h1"]),
        salary, format, country, city,
        about
      });
    } catch (e) {
      results.push({ url, error: String(e).slice(0, 120) });
    }
  }
  return results;
})()
