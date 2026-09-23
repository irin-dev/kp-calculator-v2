/*
 * main.js — фронтенд калькулятора КП (версия 2)
 * ============================================
 *
 * Принципы (из брифа ментора):
 *   1. Один вопрос на экран. Не анкета из всех полей разом.
 *   2. Кнопки вместо ввода текста + всегда вариант «Не знаю».
 *   3. Ветвление: brain (ответ) переключает на ветку A/B/C.
 *   4. Мягкие выходы нерелеванта и предложение созвона.
 *   5. Прогресс-бар, чтобы клиент видел, что финиш близко.
 *   6. Сохранение прогресса в localStorage — вышел и вернулся, квиз с того же места.
 *   7. Считает всегда сервер (POST /api/estimate): формула живёт в calculator.py,
 *      фронтенд её НЕ дублирует — это единый источник истины.
 */
(function () {
  "use strict";

  let quiz, config, state;

  const API = "/api/estimate";
  const LS_KEY = "kp-calculator-v2-state";

  // Карта id экрана → объект экрана из quiz.json (соберём после загрузки)
  const byId = {};

  // Примерное число шагов по ветке — для счётчика «Вопрос N из M»
  const TOTAL_STEPS = { scripted: 9, ai: 10 };

  // ---- helpers -------------------------------------------------------------
  const el = (id) => document.getElementById(id);

  function show(id) {
    ["step-type", "step-ready", "step-quiz", "step-special", "step-contact", "step-result"].forEach(
      (s) => el(s).classList.toggle("hidden", s !== id)
    );
  }

  function escHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  const fmtMoney = (n) => new Intl.NumberFormat("ru-RU").format(n) + " ₽";

  // ---- сохранение/восстановление прогресса ---------------------------------
  function saveState() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({
        answers: state.answers,
        path: state.path,
        special: state.special,
      }));
    } catch (e) { /* приватный режим — не критично */ }
  }

  function restoreState() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      state.answers = saved.answers || {};
      state.path = saved.path && saved.path.length ? saved.path : ["__intro"];
      state.special = saved.special || null;
    } catch (e) { /* повреждённый кеш — просто начинаем заново */ }
  }

  // ---- загрузка данных -------------------------------------------------------
  async function loadData() {
    const [q, c] = await Promise.all([
      fetch("/data/quiz.json").then((r) => r.json()),
      fetch("/config.json").then((r) => r.json()),
    ]);
    quiz = q;
    config = c.company || {};
    q.screens.forEach((s) => (byId[s.id] = s));
  }

  // ---- расчёт на сервере -----------------------------------------------------
  async function apiEstimate(answers) {
    const r = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(answers || {}),
    });
    return r.json();
  }

  // ---- Шаг 0: тип (готовый продукт / бот под ключ) --------------------------
  function renderType() {
    el("step-type").addEventListener("click", (e) => {
      const card = e.target.closest(".type-card");
      if (!card) return;
      state.type = card.dataset.type;
      if (state.type === "ready") {
        renderReady();
      } else {
        startQuiz();
      }
    });
  }

  // ---- Шаг 1: готовые продукты (как в v1, тарифный блок) --------------------
  function renderReady() {
    const sel = el("ready-product");
    sel.innerHTML = Object.entries(quizReadyProducts())
      .map(([id, p]) => `<option value="${id}">${p.name}</option>`)
      .join("");
    sel.addEventListener("change", () => renderTariffs());
    renderTariffs();
    el("ready-next").onclick = () => renderReadyResult();
    show("step-ready");
  }

  function quizReadyProducts() {
    // Готовые продукты в v2 читаем из quiz.json (блок «ready»).
    // Если его там нет — используем заглушку, чтобы страница не падала.
    return quiz.ready || {};
  }

  function renderTariffs() {
    const pid = el("ready-product").value;
    const product = quizReadyProducts()[pid];
    if (!product) return;
    const box = el("ready-tariffs");
    box.innerHTML = product.tariffs
      .map((t) => {
        const price = t.price == null ? "Индивидуально" : fmtMoney(t.price);
        return `
          <label class="opt ${state.readyTariff === t.id ? "selected" : ""}" data-tariff="${t.id}">
            <input type="radio" name="ready-tariff" value="${t.id}">
            <div>
              <div class="tariff-name">${escHtml(t.name)}</div>
              <div class="tariff-price">${price}</div>
              <div class="tariff-note muted">${escHtml(t.note || "")}</div>
            </div>
          </label>`;
      })
      .join("");
    box.querySelectorAll(".opt").forEach((o) =>
      o.addEventListener("click", () => {
        state.readyTariff = o.dataset.tariff;
        renderTariffs();
      })
    );
  }

  // ---- Результат готового продукта -------------------------------------------
  function renderReadyResult() {
    const pid = el("ready-product").value;
    const product = quizReadyProducts()[pid];
    if (!product || !state.readyTariff) { alert("Выберите тариф."); return; }
    const tariff = product.tariffs.find((t) => t.id === state.readyTariff);
    if (!tariff) return;

    const price = tariff.price;
    const included = tariff.included || [];
    state.result = {
      branch: "ready",
      price: price ? { min: price, max: price, estimate: price } : null,
      terms: tariff.term || "",
      included,
      included_ai: [],
      score: { heat: "hot", budget_fork: "фикс. тариф", reasons: ["готовый продукт"] },
      consult: { needed: false, reasons: [] },
    };

    show("step-result");
    const box = el("result-summary");
    if (!price) {
      box.innerHTML = `<div class="score-pill">Индивидуально</div>
        <p class="muted">Свяжемся и обсудим детали.</p>`;
    } else {
      box.innerHTML = `
        <div class="score-pill">${escHtml(product.name)} · фикс. тариф</div>
        ${product.describe ? `<p class="muted product-desc">${escHtml(product.describe)}</p>` : ""}
        <div class="price-vilka">${fmtMoney(price)}</div>
        <div class="price-note muted">${escHtml(tariff.note || "")}</div>
        <div class="block"><div class="block-title">Что входит</div><ul>${included.map((x) => `<li>${escHtml(x)}</li>`).join("")}</ul></div>`;
    }
    el("result-next").innerHTML = `
      <button class="btn" onclick="window.open('${escAttr(config.telegram ? "https://t.me/" + config.telegram.replace("@", "") : "#")}', '_blank')">👋 Обсудить с разработчиком</button>`;
    el("btn-kp").onclick = buildKP;
  }

  // ---- Шаг 2: воронка -------------------------------------------------------
  function startQuiz() {
    state.answers = {};
    state.path = ["__intro"];
    state.special = null;
    localStorage.removeItem(LS_KEY);
    renderIntro();
  }

  function renderIntro() {
    show("step-quiz");
    el("quiz-counter").textContent = "";
    el("quiz-progress").style.width = "0%";
    el("quiz-title").textContent = quiz.intro || "Посчитаем стоимость бота";
    el("quiz-hint").textContent = "";
    el("quiz-body").innerHTML = "";
    el("quiz-next").textContent = "Начать →";
    el("quiz-prev").disabled = true;
    state.path = ["__intro"];
    saveState();
    // Кнопка «Начать» → сразу на первый вопрос, без apiEstimate
    el("quiz-next").onclick = () => renderNextQuestion("purpose");
  }

  // Показывает вопрос: один экран, кнопки-опции.
  function renderQuestion(screenId, backPossible) {
    const screen = byId[screenId];
    if (!screen) {
      showResult();
      return;
    }
    // Экран контактов — у него нет options, рисуем отдельно
    if (screen.type === "contact") {
      renderContact();
      return;
    }
    show("step-quiz");
    // Пушим экран в путь, но не дублируем, если это уже последний
    // (случай восстановления из localStorage — там путь уже содержит экран)
    if (state.path[state.path.length - 1] !== screenId) {
      state.path.push(screenId);
    }
    saveState();

    // Счётчик: «Вопрос 3 из 9»
    const branch = detectBranchLocal();
    const total = TOTAL_STEPS[branch] || 9;
    const asked = state.path.filter((s) => s !== "__intro" && s !== "consult" && s !== "__soft_exit").length - 1;
    el("quiz-counter").textContent = `Вопрос ${Math.max(1, asked + 1)} из ${total}`;
    el("quiz-progress").style.width = `${Math.min(100, (asked / total) * 100)}%`;

    el("quiz-title").textContent = screen.question;
    el("quiz-hint").textContent = screen.hint || "";
    el("quiz-next").textContent = screen.type === "multi" ? "Далее →" : "Далее →";

    // Опции — кнопки
    const body = el("quiz-body");
    body.innerHTML = screen.options
      .map((o, i) => {
        const sel = isSelected(screen.id, o.value);
        const mark = isMulti(screen.id) ? "☑ " : (sel ? "● " : "○ ");
        return `<button type="button" class="opt-btn ${sel ? "selected" : ""}" data-val="${o.value}">
          ${o.emoji ? o.emoji + " " : ""}${escHtml("" + mark + o.label)}
        </button>`;
      })
      .join("");

    body.querySelectorAll(".opt-btn").forEach((btn) =>
      btn.addEventListener("click", () => {
        const val = btn.dataset.val;
        pickOption(screen, val, btn);
      })
    );

    el("quiz-prev").disabled = !backPossible;
    el("quiz-next").onclick = () => advance(screen.id);
  }

  const isMulti = (id) => byId[id] && byId[id].type === "multi";
  const isSelected = (id, val) => {
    const v = state.answers[id];
    return Array.isArray(v) ? v.includes(val) : v === val;
  };

  function pickOption(screen, val, btn) {
    if (screen.type === "multi") {
      const arr = Array.isArray(state.answers[screen.id]) ? [...state.answers[screen.id]] : [];
      const i = arr.indexOf(val);
      i >= 0 ? arr.splice(i, 1) : arr.push(val);
      state.answers[screen.id] = arr;
      btn.classList.toggle("selected", arr.includes(val));
    } else {
      state.answers[screen.id] = val;
      document.querySelectorAll("#quiz-body .opt-btn").forEach((b) =>
        b.classList.toggle("selected", b === btn)
      );
    }
  }

  // Куда идём дальше: у опции есть свой next (ветвление), иначе default экрана
  function resolveNext(screen, answers) {
    const picked = answers[screen.id];
    if (screen.options && !isMulti(screen.id)) {
      const opt = screen.options.find((o) => o.value === picked);
      if (opt && opt.next) return opt.next;
    }
    return screen.next;
  }

  function detectBranchLocal() {
    const b = state.answers.brain;
    if (b === "scripted" || b === "ai") return b;
    return "scripted"; // до ответа на brain показываем дефолт (9 шагов)
  }

  // Переход после ответа: проверяем мягкий выход → спец-экран, иначе вопрос
  async function advance(screenId) {
    // __intro обрабатывается отдельно в renderIntro
    if (screenId === "__intro") { renderNextQuestion("purpose"); return; }
    const screen = byId[screenId];
    let nextId = resolveNext(screen, state.answers);
    el("quiz-next").disabled = true;

    // Мягкий выход / созвон: спрашиваем сервер, пока кнопка неактивна
    let est = null;
    try { est = await apiEstimate(state.answers); } catch (e) { /* сеть оффлайн — идём дальше */ }
    state.result = est;

    // Мягкий выход (бюджет «до 30к» + AI): показываем вместо следующего вопроса
    if (est && est.soft_exit) {
      renderSpecial("exit", est.soft_exit, nextId);
      return;
    }

    // Экран созвона — только если это явный переход по ветке (brain: гибрид/помогите)
    if (nextId === "consult") {
      renderSpecial("consult", null, "deadline");
      return;
    }

    renderNextQuestion(nextId);
  }

  function renderIntroNext(nextId) {
    // Кнопка «Начать» на интро → переносим на "purpose" без «Далее» по умолчанию
    show("step-quiz");
    renderNextQuestion("purpose");
  }

  function renderNextQuestion(nextId) {
    el("quiz-next").disabled = false;
    renderQuestion(nextId, state.path.length > 1);
  }

  // ---- Шаг 3: спец-экран (созвон / мягкий выход) ----------------------------
  function renderSpecial(kind, data, resumeId) {
    show("step-special");
    state.special = { kind, resumeId };
    saveState();

    if (kind === "exit") {
      el("special-emoji").textContent = "🫂";
      el("special-title").textContent = data.title;
      el("special-text").innerHTML = escHtml(data.message);
      el("special-next").textContent = "Всё равно посчитать →";
    } else {
      el("special-emoji").textContent = "📞";
      el("special-title").textContent = quiz.consult.title;
      el("special-text").innerHTML = escHtml(quiz.consult.text);
      el("special-next").textContent = "Продолжить расчёт →";
    }
  }

  // ---- Шаг 4: контакты + ПДн -------------------------------------------------
  function renderContact() {
    show("step-contact");
    const body = el("contact-options");
    const options = [
      { value: "in_chat", label: "В этот чат" },
      { value: "email", label: "На почту", input: "email", placeholder: "name@company.ru" },
      { value: "messenger", label: "В мессенджер", input: "text", placeholder: "+7 (___) ___-__-__ / @username" },
    ];
    body.innerHTML = options
      .map((o) => `<button type="button" class="opt-btn ${state.answers.contact === o.value ? "selected" : ""}" data-val="${o.value}">○ ${escHtml(o.label)}</button>`)
      .join("");
    let select = (btn, val) => {
      state.answers.contact = val;
      body.querySelectorAll(".opt-btn").forEach((b) => b.classList.toggle("selected", b === btn));
      renderContactFields(options.find((o) => o.value === val));
    };
    body.querySelectorAll(".opt-btn").forEach((btn) =>
      btn.addEventListener("click", () => select(btn, btn.dataset.val))
    );
    el("contact-quote").textContent = quiz.pd.quote;
    renderContactFields(options.find((o) => o.value === state.answers.contact));
    el("contact-next").onclick = () => finishContact();
  }

  function renderContactFields(opt) {
    const box = el("contact-fields");
    const val = state.answers.contact_value || "";
    box.innerHTML = opt && opt.input
      ? `<label class="field"><span>${escHtml(opt.label)}</span>
           <input type="${opt.input}" value="${escHtml(val)}" placeholder="${escHtml(opt.placeholder)}"></label>`
      : "";
    const inp = box.querySelector("input");
    if (inp) inp.addEventListener("input", () => (state.answers.contact_value = inp.value));
  }

  async function finishContact() {
    if (!state.answers.contact) { alert("Выберите, куда прислать КП."); return; }
    if (!el("pd-consent").checked) { alert("Нужно согласие на обработку персональных данных."); return; }
    state.answers.pd_consent = true;
    renderResult();
  }

  // ---- Шаг 5: результат -------------------------------------------------------
  async function renderResult() {
    let est = state.result;
    try { est = await apiEstimate(state.answers); } catch (e) { /* */ }
    state.result = est;
    show("step-result");

    const price = est.price;
    const box = el("result-summary");

    if (!price) {
      box.innerHTML = `
        <div class="score-pill">${est.branch === "hybrid" ? "Гибрид — обсудим вживую" : "Оценим на созвоне"}</div>
        <p class="muted">У проекта есть нюансы — соединимся на 15 минут и посчитаем точно.</p>`;
    } else {
      const heatLabel = { hot: "🔥 горячий", warm: "🌤 тёплый", cold: "🗂 холодный" }[est.score.heat] || est.score.heat;
      box.innerHTML = `
        <div class="score-pill">${est.branch === "ai" ? "AI-бот" : "Сценарный бот"} · лид: ${heatLabel} · бюджет ${escHtml(est.score.budget_fork)}</div>
        <div class="price-vilka">${fmtMoney(price.min)} — ${fmtMoney(price.max)}</div>
        <div class="price-note muted">середина ≈ ${fmtMoney(price.estimate)} · срок: ${escHtml(est.terms || "")}</div>
        <div class="block"><div class="block-title">Что входит</div><ul>${est.included.map((x) => `<li>${escHtml(x)}</li>`).join("")}</ul></div>`;
      if (est.consult && est.consult.needed) {
        box.innerHTML += `<div class="consult-hint">💬 Вижу нюансы (${escHtml(est.consult.reasons.join(", "))}) — на созвоне зафиксируем точную цену.</div>`;
      }
    }

    // Кнопки действий
    el("result-next").innerHTML = `
      <button class="btn" onclick="window.open('${escAttr(config.telegram ? "https://t.me/" + config.telegram.replace("@", "") : "#")}', '_blank')">👋 Обсудить с разработчиком</button>`;

    el("btn-kp").onclick = buildKP;
  }

  // ---- КП: генерация HTML-документа (как в v1, но с вилкой) ------------------
  function buildKP() {
    const est = state.result;
    const c = config;
    const today = new Date().toLocaleDateString("ru-RU");
    const isReady = !!(est && est.branch === "ready");

    function line(s) { return `<li>${escHtml(s)}</li>`; }

    let priceLine = "по результатам созвона";
    let body;
    if (!est || !est.price) {
      body = `<ul><li><b>Услуга:</b> разработка чат-бота (обсуждается на созвоне)</li></ul>`;
    } else if (isReady) {
      // Готовый продукт — фиксированная цена, вилка не нужна
      priceLine = fmtMoney(est.price.min);
      body = `
        <ul>
          <li><b>Фиксированный тариф:</b> ${fmtMoney(est.price.min)}</li>
          ${est.terms ? `<li><b>Срок:</b> ${escHtml(est.terms)}</li>` : ""}
          <li><b>Что входит:</b><ul>${est.included.map((x) => line(x)).join("")}</ul></li>
          <li><b>Тариф зафиксирован — детали запуска обсудим на коротком созвоне (15 минут).</b></li>
        </ul>`;
    } else {
      // Разработка под ключ — вилка стоимости
      priceLine = `${fmtMoney(est.price.min)} — ${fmtMoney(est.price.max)}`;
      body = `
        <ul>
          <li><b>Вилка стоимости:</b> ${fmtMoney(est.price.min)} — ${fmtMoney(est.price.max)}</li>
          <li><b>Ориентировочная середина:</b> ${fmtMoney(est.price.estimate)}</li>
          <li><b>Срок:</b> ${escHtml(est.terms || "")}</li>
          <li><b>Что входит:</b><ul>${est.included.map((x) => line(x)).join("")}</ul></li>
          <li><b>Точную цену зафиксируем на коротком созвоне (15 минут).</b></li>
        </ul>`;
    }

    const html = `<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>КП ${today}</title>
<style>
  body { font-family: -apple-system, "Segoe UI", Arial, sans-serif; color: #1f2437; max-width: 800px; margin: 24px auto; padding: 24px; line-height: 1.55; }
  h1 { font-size: 1.4rem; margin: 0 0 4px; }
  .logo-line { color: #4f46e5; font-weight: 700; }
  .meta { color: #6b7280; font-size: .9rem; margin: 6px 0; }
  .hr { border: none; border-top: 2px solid #4f46e5; margin: 16px 0; }
  .price { font-size: 1.35rem; font-weight: 800; color: #3730a3; margin: 12px 0; }
  ul { margin: 8px 0; padding-left: 20px; }
  .foot { margin-top: 32px; font-size: .85rem; color: #6b7280; border-top: 1px solid #e5e7eb; padding-top: 12px; }
  .print-btn { background: #4f46e5; color: #fff; border: none; padding: 10px 18px; border-radius: 8px; cursor: pointer; }
  @media print { .print-btn { display: none; } }
</style></head><body>
  <div class="logo-line">${escHtml(c.name)}</div>
  <div class="meta">${escHtml(c.tagline)}</div>
  <div class="hr"></div>
  <h1>Коммерческое предложение</h1>
  <div class="meta">№ ${Date.now().toString().slice(-6)} от ${today}</div>
  <div class="price">${priceLine}</div>
  <h3>Состав предложения</h3>${body}
  <h3>Следующий шаг</h3>
  <p>Ответьте на это письмо или напишите в Telegram — созвонимся на 15 минут и зафиксируем точную цену, сроки и договор.</p>
  <div class="foot">
    <p><b>Реквизиты:</b> ${escHtml(c.legal)}</p>
    <p>Телефон: ${escHtml(c.phone)} · Email: ${escHtml(c.email)} · Telegram: ${escHtml(c.telegram)}</p>
    <p>Предложение действительно 14 дней. Данные обработаны с согласия (152-ФЗ) и используются только для этого КП.</p>
  </div>
  <button class="print-btn" onclick="window.print()">Сохранить в PDF / печать</button>
</body></html>`;

    const w = window.open("", "_blank");
    w.document.write(html);
    w.document.close();
  }

  function escAttr(s) {
    return escHtml(s).replace(/`/g, "&#96;");
  }

  // ---- навигация назад -------------------------------------------------------
  function goBack() {
    // Убираем последний шаг пути и идём к предыдущему «настоящему» экрану
    while (state.path.length > 1) {
      state.path.pop();
      const prev = state.path[state.path.length - 1];
      if (prev === "__intro") { renderIntro(); return; }
      if (prev === "consult" || prev === "__soft_exit") continue;
      renderQuestion(prev, state.path.length > 1);
      return;
    }
    renderType();
    show("step-type");
  }

  // ---- кнопки «Назад», «Продолжить» на спец-экранах --------------------------
  function bindQuizButtons() {
    el("quiz-prev").addEventListener("click", goBack);

    el("special-next").addEventListener("click", () => {
      const resumeId = state.special ? state.special.resumeId : "deadline";
      state.special = null;
      renderNextQuestion(resumeId);
    });
    el("special-back").addEventListener("click", goBack);

    el("contact-back").addEventListener("click", () => {
      state.path.pop(); // убираем contact
      renderNextQuestion(state.path[state.path.length - 1]);
    });

    document.querySelectorAll("[data-back], [data-result-back]").forEach((b) =>
      b.addEventListener("click", () => { startQuiz(); })
    );
  }

  // ---- init --------------------------------------------------------------------
  (async function init() {
    await loadData();
    state = { type: null, readyTariff: null, answers: {}, path: ["__intro"], special: null, result: null };

    bindQuizButtons();
    renderType();

    // Пробуем восстановить незавершённый квиз того же типа
    restoreState();
    if (state.path && state.path.length > 1) {
      const lastReal = [...state.path].reverse().find((s) => s !== "consult" && s !== "__soft_exit");
      if (lastReal && byId[lastReal]) {
        show("step-quiz");
        renderQuestion(lastReal, true);
        return;
      }
    }
  })();
})();