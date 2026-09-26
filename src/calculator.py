"""
calculator.py — движок расчёта КП (версия 2)
=============================================

Что здесь происходит (для студента):
1. Мы получаем ОТВЕТЫ пользователя на вопросы квиза (словарь `answers`).
2. Определяем ВЕТКУ проекта: сценарный бот / AI-бот / гибрид.
3. Проверяем, не «мимо» ли проект (мягкие выходы) и нужен ли СОЗВОН.
4. Считаем цену по ФОРМУЛЕ (не по баллам, как в v1):
       КП = База × Платформа + Σ(интеграции) + Модуль_AI + Админка + Срочность
5. Выдаём ВИЛКУ (min–max), а не одно число — это защищает нас от
   «а почему вы говорили 80к, а теперь 120к» (в брифe ментора).
6. Собираем СКОРИНГ лида — метки для CRM (горячий/тёплый, тип, бюджет).

База `quiz` поставляется из data/quiz.json — там ВЕСА формулы и вопросы.

⚠️ Матрица цен в data/quiz.json — УЧЕБНАЯ (демонстрационная). Она нужна,
чтобы формула считала, а не чтобы продавать по этим цифрам. В коммерческом
проекте заменяете блок `weights` и каталог `ready` на свои значения.
"""
import json
import os

# ---------------------------------------------------------------------------
# Пути к файлам
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # src/
DATA_DIR = os.path.join(BASE_DIR, "..", "data")                # data/
ROOT_DIR = os.path.dirname(BASE_DIR)                            # edu/kp-calculator-v2/


def load_quiz():
    """Загружает структуру квиза (вопросы + веса) из data/quiz.json."""
    with open(os.path.join(DATA_DIR, "quiz.json"), encoding="utf-8") as f:
        return json.load(f)


def load_answers():
    """Пустой словарь ответов — удобно как отправная точка для отладки."""
    return {}


# ---------------------------------------------------------------------------
# Шаг 1. Ветка проекта
# ---------------------------------------------------------------------------
def detect_branch(answers, quiz=None):
    """
    Определяем тип проекта по вопросу `brain` (как бот будет отвечать).

    Возможные ветки:
      * scripted — сценарный бот (кнопки, FAQ, формы)
      * ai       — ИИ-бот (понимает свободные вопросы)
      * hybrid   — гибрид (бот + живой менеджер)
      * unknown  — ответ не выбран (ранний этап квиза)

    Гибрид и «помогите определить» сразу ведут на созвон, поэтому
    сами по себе они не считаются полноценной веткой для формулы.
    """
    quiz = quiz or load_quiz()
    brain = answers.get("brain")
    # Если ответа нет — это ещё не ветка
    if brain in ("scripted", "ai", "hybrid"):
        return brain
    return "unknown"


# ---------------------------------------------------------------------------
# Шаг 2. Собираем весовые слагаемые из ответов
# ---------------------------------------------------------------------------
def _picked(answers, screen_id):
    """Возвращает выбранные значения экрана: ['tg','wa'] или []."""
    v = answers.get(screen_id)
    if not v:
        return []
    if isinstance(v, (list, tuple, set)):
        return list(v)
    return [v]


def _first(answers, screen_id):
    """Возвращает первое выбранное значение или None (для single-вопросов)."""
    picked = _picked(answers, screen_id)
    return picked[0] if picked else None


def collect_parameters(answers, quiz=None):
    """
    Превращает ответы в «параметры расчёта» — словарь понятный формуле.

    Сюда входят:
      * branch        — ветка (scripted / ai / hybrid)
      * platforms     — список платформ
      * is_multi      — выбрана ли опция «мультиплатформа»
      * integrations  — сумма денежных весов за интеграции (рубли)
      * admin_panel   — нужна ли админ-панель (bool)
      * ai_module     — вклад модуля AI: база знаний / дообучение (рубли)
      * local_only    — данные нельзя в облако (множитель ×1.6)
      * urgent        — срочность (множитель ×1.3)

    ⚙️ Как отличаем «рубль» от «множителя» в таблице весов (quiz.json):
       * веса ≥ 1000  → это денежное слагаемое (интеграция = +10 000 ₽)
       * веса < 100   → это множитель (1.3, 1.5, 2.0…) — входит во всю цену
    Это простое правило держит quiz.json декларативным: добавить опцию =
    добавить `"weight": "название_веса"` в одну строчку.
    """
    quiz = quiz or load_quiz()
    w = quiz["weights"]                       # таблица весов из quiz.json
    branch = detect_branch(answers, quiz)

    # --- Платформы ---------------------------------------------------------
    platforms = _picked(answers, "platform")
    is_multi = "multi" in platforms

    # --- Проходим по всем экранам и собираем веса выбранных опций ---------
    integrations = 0       # сумма за интеграции (рубли)
    ai_module = 0          # вклад модуля AI: база знаний / RAG (рубли)
    admin_panel = False
    local_only = False
    urgent = False

    for screen in quiz["screens"]:
        values = _picked(answers, screen["id"])
        for opt in screen.get("options", []):
            weight_key = opt.get("weight")           # например "integration_crm"
            if not weight_key or opt["value"] not in values:
                continue
            val = w.get(weight_key)
            if val is None:
                continue

            # Множители (вес < 100): сразу смотрим их смысл по имени веса
            if val < 100:
                if weight_key == "local_multiplier":
                    local_only = True
                elif weight_key == "urgency_multiplier":
                    urgent = True
                continue

            # Денежные слагаемые (вес ≥ 1000)
            number = float(val)
            if weight_key in ("integration_crm", "integration_payments", "integration_sheets"):
                integrations += number
            elif weight_key == "admin_panel":
                admin_panel = True
            elif weight_key in ("ai_knowledge", "ai_finetune"):
                ai_module += number

    return {
        "branch": branch,
        "platforms": platforms,
        "is_multi": is_multi,
        "integrations": integrations,
        "admin_panel": admin_panel,
        "ai_module": ai_module,
        "local_only": local_only,
        "urgent": urgent,
    }


# ---------------------------------------------------------------------------
# Шаг 3. Вилка цены по формуле
# ---------------------------------------------------------------------------
def round_to_thousand(value):
    """Округляет до целой тысячи рублей — цены в КП «человеческие»."""
    return int(round(value / 1000.0) * 1000)


def estimate_range(answers, quiz=None):
    """
    Считает вилку стоимости по формуле:

        КП = База × Платформа + Σ(интеграции) + Модуль_AI + Админка + Срочность

    Принцип «вилки»:
      * estimate = «середина» по ответам (дефолтная конфигурация)
      * min      = estimate × range_min_factor (0.9)  — «простая» конфигурация
      * max      = estimate × range_max_factor (1.3)  — запас на нюансы

    Так мы называем цену честно, но оставляем себе свободу до созвона.
    """
    quiz = quiz or load_quiz()
    w = quiz["weights"]
    p = collect_parameters(answers, quiz)

    if p["branch"] not in ("scripted", "ai"):
        # Для гибрида / «пока не знаю» точную цену не считаем — ведём на созвон
        return None

    # 1) База — самый дешёвый вариант данной ветки
    base = w["base"][p["branch"]]

    # 2) Множитель платформ
    #    Первая платформа уже учтена в `base`, каждая ДОП. платформа = ×1.3.
    #    Если выбрана «мультиплатформа» — берём сразу ×1.8.
    if p["is_multi"]:
        platform_mult = w["platform_multi"]
    else:
        extras = max(0, len(p["platforms"]) - 1)      # доп. платформы после первой
        platform_mult = 1.0 + extras * (w["platform_extra"] - 1.0)

    # 3) Сумма интеграций + админка (денежные веса опций)
    adders = p["integrations"]
    if p["admin_panel"]:
        adders += w["admin_panel"]

    # 4) Модуль AI (база знаний / дообучение) — уже собран в параметрах
    ai_module = p["ai_module"]

    # 5) Множители: локальное развёртывание и срочность
    scale = 1.0
    if p["local_only"]:
        scale *= w["local_multiplier"]
    if p["urgent"]:
        scale *= w["urgency_multiplier"]

    # 6) Итоговая «середина»
    estimate = (base * platform_mult + adders + ai_module) * scale
    estimate = round_to_thousand(estimate)

    # 7) Вилка
    low  = round_to_thousand(estimate * w["range_min_factor"])
    high = round_to_thousand(estimate * w["range_max_factor"])

    return {
        "estimate": estimate,
        "min": low,
        "max": high,
        "base": base,
        "platform_mult": round(platform_mult, 2),
        "adders": adders,
        "ai_module": ai_module,
        "scale": round(scale, 2),
    }


# ---------------------------------------------------------------------------
# Шаг 4. Мягкие выходы нерелеванта и триггеры созвона
# ---------------------------------------------------------------------------
def check_soft_exit(answers, quiz=None):
    """
    Проверяет «мягкие выходы»: джентльменно, но честно —
    либо проект «мимо» бюджета, либо человек просто смотрит.
    Возвращает сообщение для показа ИЛИ None (всё ок, идём дальше).
    """
    quiz = quiz or load_quiz()
    branch = detect_branch(answers, quiz)
    budget = answers.get("budget")
    purpose = answers.get("purpose")

    # «До 30к» + AI/гибрид = нерелевант по бюджету (см. бриф, ТОЧКА ОСТАНОВКИ 1)
    if budget == "below_30k" and branch in ("ai", "hybrid"):
        return quiz["soft_exits"]["low_budget_ai"]

    # «Просто интересуюсь» — ничего не планирует
    if purpose == "not_sure" and budget == "not_sure":
        return quiz["soft_exits"]["just_curious"]

    return None


def check_consult(answers, quiz=None):
    """
    Когда предлагаем созвон (по брифу):
      * выбрано «Помогите определить» или «Гибрид» (ветка → consult)
      * 3+ ответа «не знаю» (вариант not_sure)
      * бюджет выше 100 000 ₽ — есть смысл пообщаться лично
    Возвращает список причин + флаг `needed`.
    """
    quiz = quiz or load_quiz()
    reasons = []

    branch = detect_branch(answers, quiz)
    if branch == "hybrid":
        reasons.append("выбран гибрид «бот + менеджер»")
    if answers.get("brain") == "help_me":
        reasons.append("выбрано «помогите определить»")

    # Подсчёт «не знаю» по всем экранам
    not_sure_count = 0
    for v in answers.values():
        vals = v if isinstance(v, (list, tuple, set)) else [v]
        not_sure_count += sum(1 for x in vals if x == "not_sure")
    threshold = quiz["rules"]["consult_threshold_notsure"]
    if not_sure_count >= threshold:
        reasons.append(f"{threshold}+ ответа «не знаю»")

    # Бюджет выше минимальной планки — личное общение
    if answers.get("budget") in quiz["rules"]["consult_min_budget"]:
        reasons.append("бюджет проекта больше 100 000 ₽")

    return {"needed": bool(reasons), "reasons": reasons}


# ---------------------------------------------------------------------------
# Шаг 5. Скоринг лида (метки для CRM-системы)
# ---------------------------------------------------------------------------
def lead_score(answers, quiz=None):
    """
    Возвращает метки для CRM:
      * heat        — горячий / тёплый / холодный
      * branch      — тип бота (scripted / ai / hybrid)
      * budget_fork — вилка бюджета человеческим языком
    """
    quiz = quiz or load_quiz()
    budget = answers.get("budget")
    decision = answers.get("decision")
    branch = detect_branch(answers, quiz)

    budget_labels = {
        "below_30k": "до 30к",
        "mid_30_100": "30–100к",
        "high_100_300": "100–300к",
        "premium_300": "300к+",
        "not_sure": "не знаю",
    }

    # Логика «тепла»:
    #   горячий — решает сам + бюджет от 100к
    #   тёплый  — решает сам + бюджет 30–100к (или есть понимание)
    #   холодный — тендер / «интересуюсь»
    if decision == "self" and budget in ("high_100_300", "premium_300"):
        heat = "hot"
    elif decision == "self" and budget in ("mid_30_100", "below_30k"):
        heat = "warm"
    else:
        heat = "cold"

    return {
        "heat": heat,
        "branch": branch,
        "budget_fork": budget_labels.get(budget, "неизвестно"),
    }


def estimate_terms(answers, quiz=None):
    """
    Ориентировочные сроки запуска — показываем рядом с вилкой цены.

    Логика (простая эвристика для КП):
      * сценарный бот без интеграций → 1–2 недели
      * сценарный с интеграциями/админкой → 2–3 недели
      * AI-бот → 2–4 недели
      * AI + локальное развёртывание или дообучение → 3–5 недель
      * срочный заказ → указываем, что будет приоритет в очереди
    """
    quiz = quiz or load_quiz()
    p = collect_parameters(answers, quiz)
    takes = 0                       # ~количество недель (нижняя граница)
    if p["branch"] == "scripted":
        takes = 1 if not (p["integrations"] or p["admin_panel"]) else 2
    else:
        takes = 2
        if p["local_only"] or p["ai_module"]:
            takes += 1
    text = f"{takes}–{takes + 1} недели"
    if p["urgent"]:
        text += " · срочный запуск (приоритет)"
    return text


# ---------------------------------------------------------------------------
# Шаг 6. Сборка всего результата (то, что покажет квиз и фронтенд)
# ---------------------------------------------------------------------------
def evaluate(answers, quiz=None):
    """
    Главная функция для фронтенда: собирает ВСЁ в один словарь.
    Фронтенд просто показывает поля; считать сам ничего не должен.
    """
    quiz = quiz or load_quiz()
    branch = detect_branch(answers, quiz)
    soft_exit = check_soft_exit(answers, quiz)
    consult = check_consult(answers, quiz)
    price = estimate_range(answers, quiz)

    # «Что входит» собираем из списка аддеров (для красивого списка в КП)
    included = []
    if branch == "scripted":
        included.append("Разработка бота по сценарию (кнопки, меню)")
        if "faq" in _picked(answers, "capabilities"):
            included.append("FAQ-блок")
        if _picked(answers, "integrations"):
            included.extend(("Интеграция с выбранными системами",))
        if "admin" in _picked(answers, "capabilities"):
            included.append("Панель управления для менеджера")
    elif branch == "ai":
        included.append("ИИ-бот с ответами по вашей базе знаний")
        if "knowledge" in _picked(answers, "ai_base") or "finetune" in _picked(answers, "ai_base"):
            included.append("Загрузка и настройка базы знаний")
        if answers.get("ai_constraints") == "local_only":
            included.append("Развёртывание в вашем контуре (без облака)")
    included.append("Договор, передача, консультация по запуску")

    return {
        "branch": branch,
        "soft_exit": soft_exit,
        "consult": consult,
        "price": price,
        "terms": estimate_terms(answers, quiz) if price else None,
        "included": included,
        "score": lead_score(answers, quiz),
    }


# ---------------------------------------------------------------------------
# Быстрая самопроверка при запуске файла (python src/calculator.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test = {
        "purpose": "sell",
        "budget": "mid_30_100",
        "platform": ["tg", "wa"],
        "brain": "scripted",
        "capabilities": ["faq", "booking"],
        "integrations": ["crm"],
        "deadline": "no_rush",
        "decision": "self",
    }
    res = evaluate(test)
    print("Vetka:", res["branch"])
    print("Vilka:", res["price"]["min"], "-", res["price"]["max"], "RUB")
    print("Vhodit:", "; ".join(res["included"]))
    print("Lid:", res["score"])