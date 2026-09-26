"""
test_calculator.py — тесты движка расчёта КП (версия 2)
========================================================

Запуск (из папки edu/kp-calculator-v2):
    python -m unittest tests.test_calculator -v
или просто:
    python tests/test_calculator.py

Покрываем:
  * формулу для сценарной и AI-ветки (включая множители платформ),
  * вилку (min <= estimate <= max) во всех сценариях,
  * триггеры созвона (гибрид / «помогите» / 3+ «не знаю» / бюджет > 100к),
  * мягкие выходы нерелеванта (до 30к + AI; «просто интересуюсь»),
  * скоринг лида (горячий/тёплый/холодный).
"""
import os
import sys
import unittest

# Подключаем src/ в путь импорта, чтобы можно было `import calculator`
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from calculator import (
    collect_parameters,
    detect_branch,
    evaluate,
    estimate_range,
    check_soft_exit,
    check_consult,
    lead_score,
)


# ---------------------------------------------------------------------------
# Вспомогательные наборы «образцовых» ответов для быстрой перестановки
# ---------------------------------------------------------------------------
def scripted_answers(**overrides):
    """Минимальный набор ответов для сценарной ветки."""
    base = {
        "purpose": "sell",
        "budget": "mid_30_100",
        "platform": ["tg"],
        "brain": "scripted",
        "capabilities": ["faq"],
        "integrations": ["none"],
        "deadline": "no_rush",
        "decision": "self",
    }
    base.update(overrides)
    return base


def ai_answers(**overrides):
    """Минимальный набор ответов для AI-ветки."""
    base = {
        "purpose": "ai_sales",
        "budget": "high_100_300",
        "platform": ["tg"],
        "brain": "ai",
        "ai_base": "general",
        "ai_constraints": "none",
        "ai_fallback": "handoff",
        "deadline": "no_rush",
        "decision": "self",
    }
    base.update(overrides)
    return base


class TestBranchAndParams(unittest.TestCase):
    """Шаг 1: определение ветки и сбор параметров."""

    def test_detect_branch_scripted(self):
        self.assertEqual(detect_branch({"brain": "scripted"}), "scripted")

    def test_detect_branch_ai(self):
        self.assertEqual(detect_branch({"brain": "ai"}), "ai")

    def test_detect_branch_unknown_without_answer(self):
        self.assertEqual(detect_branch({}), "unknown")

    def test_collect_parameters_extra_platform(self):
        # Две платформы → они просто попадают в список platforms
        p = collect_parameters(scripted_answers(platform=["tg", "wa"]))
        self.assertEqual(p["platforms"], ["tg", "wa"])
        self.assertFalse(p["is_multi"])

    def test_collect_parameters_multiplatform(self):
        p = collect_parameters(scripted_answers(platform=["multi"]))
        self.assertTrue(p["is_multi"])

    def test_collect_parameters_integrations_and_admin(self):
        p = collect_parameters(scripted_answers(
            capabilities=["faq", "admin"],
            integrations=["crm", "pay"],
        ))
        # CRM 8 000 + платёжка 12 000
        self.assertEqual(p["integrations"], 20000)
        self.assertTrue(p["admin_panel"])

    def test_collect_parameters_ai_module(self):
        p = collect_parameters(ai_answers(ai_base="finetune"))
        self.assertEqual(p["ai_module"], 30000)  # дообучение

    def test_collect_parameters_local_and_urgent(self):
        p = collect_parameters(ai_answers(
            ai_constraints="local_only",
            deadline="urgent",
        ))
        self.assertTrue(p["local_only"])
        self.assertTrue(p["urgent"])


class TestFormula(unittest.TestCase):
    """Шаг 3: формула и вилка цены."""

    def test_scripted_base_min_platform(self):
        # 25 000 × 1.0 = 25 000 → мин 22 000, макс 31 000
        r = estimate_range(scripted_answers(platform=["tg"]))
        self.assertEqual(r["min"], 22000)
        self.assertEqual(r["max"], 31000)
        self.assertEqual(r["estimate"], 25000)

    def test_scripted_extra_platform(self):
        # 25 000 × 1.25 = 31 250 → мин 28 000, макс 39 000
        r = estimate_range(scripted_answers(platform=["tg", "wa"]))
        self.assertEqual(r["min"], 28000)
        self.assertEqual(r["max"], 39000)

    def test_ai_base(self):
        # 60 000 × 1.0 = 60 000 → мин 54 000, макс 75 000
        r = estimate_range(ai_answers())
        self.assertEqual(r["min"], 54000)
        self.assertEqual(r["max"], 75000)

    def test_ai_knowledge_local_urgent(self):
        # (60 000 + 15 000) × 1.6 × 1.3 = 156 000 → мин 140 000, макс 195 000
        r = estimate_range(ai_answers(
            ai_base="knowledge",          # +15 000 (база знаний)
            ai_constraints="local_only",  # ×1.6
            deadline="urgent",            # ×1.3
        ))
        self.assertEqual(r["estimate"], 156000)
        self.assertEqual(r["min"], 140000)
        self.assertEqual(r["max"], 195000)

    def test_hybrid_has_no_price(self):
        # Гибрид не считаем — ведём на созвон
        self.assertIsNone(estimate_range(scripted_answers(brain="hybrid")))

    def test_vilka_invariant(self):
        """Во всех сценариях: min <= estimate <= max."""
        scenarios = [
            scripted_answers(),
            scripted_answers(platform=["tg", "wa", "vk"]),
            scripted_answers(capabilities=["faq", "admin"], integrations=["crm", "pay"]),
            scripted_answers(deadline="urgent"),
            ai_answers(),
            ai_answers(ai_base="finetune", ai_constraints="local_only", deadline="urgent"),
            ai_answers(ai_base="knowledge", ai_constraints="russian"),
        ]
        for answers in scenarios:
            r = estimate_range(answers)
            self.assertIsNotNone(r, f"для {answers}")
            self.assertLessEqual(r["min"], r["estimate"], f"для {answers}")
            self.assertLessEqual(r["estimate"], r["max"], f"для {answers}")


class TestSoftExits(unittest.TestCase):
    """Шаг 4a: мягкие выходы нерелеванта."""

    def test_low_budget_ai_exit(self):
        se = check_soft_exit({**ai_answers(), "budget": "below_30k"})
        self.assertIsNotNone(se)
        self.assertEqual(se["title"], "Понимаю вас")

    def test_curious_exit(self):
        se = check_soft_exit({
            "purpose": "not_sure",
            "budget": "not_sure",
        })
        self.assertIsNotNone(se)
        self.assertEqual(se["title"], "Сориентирую")

    def test_no_exit_for_healthy_lead(self):
        self.assertIsNone(check_soft_exit(scripted_answers()))


class TestConsultTriggers(unittest.TestCase):
    """Шаг 4b: когда предлагаем созвон."""

    def test_hybrid_triggers_consult(self):
        c = check_consult(scripted_answers(brain="hybrid"))
        self.assertTrue(c["needed"])
        self.assertTrue(any("гибрид" in r for r in c["reasons"]))

    def test_help_me_triggers_consult(self):
        c = check_consult(scripted_answers(brain="help_me"))
        self.assertTrue(c["needed"])

    def test_big_budget_triggers_consult(self):
        c = check_consult(scripted_answers(budget="premium_300"))
        self.assertTrue(c["needed"])

    def test_three_not_sure_triggers_consult(self):
        answers = {
            "purpose": "not_sure",
            "budget": "not_sure",
            "platform": ["tg"],
            "brain": "scripted",
            "capabilities": ["faq"],
            "integrations": ["not_sure"],
        }
        c = check_consult(answers)
        self.assertTrue(c["needed"])
        self.assertTrue(any("не знаю" in r for r in c["reasons"]))

    def test_clear_lead_no_consult(self):
        c = check_consult(scripted_answers())
        self.assertFalse(c["needed"])


class TestLeadScore(unittest.TestCase):
    """Шаг 5: скоринг лида."""

    def test_hot_lead(self):
        s = lead_score(scripted_answers(budget="high_100_300", decision="self"))
        self.assertEqual(s["heat"], "hot")
        self.assertEqual(s["branch"], "scripted")

    def test_warm_lead_mid_budget(self):
        s = lead_score(scripted_answers(budget="mid_30_100", decision="self"))
        self.assertEqual(s["heat"], "warm")

    def test_cold_lead_tender(self):
        s = lead_score(scripted_answers(decision="tender"))
        self.assertEqual(s["heat"], "cold")

    def test_ai_branch_scoring(self):
        s = lead_score(ai_answers(budget="high_100_300", decision="self"))
        self.assertEqual(s["heat"], "hot")
        self.assertEqual(s["branch"], "ai")
        self.assertEqual(s["budget_fork"], "100–300к")


class TestEvaluate(unittest.TestCase):
    """Шаг 6: целостный результат для фронтенда."""

    def test_full_scripted(self):
        res = evaluate(scripted_answers())
        self.assertEqual(res["branch"], "scripted")
        self.assertIsNone(res["soft_exit"])
        self.assertFalse(res["consult"]["needed"])
        self.assertIsNotNone(res["price"])
        self.assertTrue(res["included"])  # «что входит» непустое
        self.assertIn("score", res)

    def test_full_ai(self):
        res = evaluate(ai_answers())
        self.assertEqual(res["branch"], "ai")
        self.assertIn("ИИ-бот", res["included"][0])


if __name__ == "__main__":
    unittest.main()