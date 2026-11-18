import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate as gen


class GenerationTests(unittest.TestCase):
    def test_currency_and_percentage(self):
        self.assertEqual(gen.price_br(1234.50), "R$ 1.234,50")
        self.assertEqual(gen.percent_br(-3.5), "3,50%")

    def test_events_filter(self):
        today = dt.date(2026, 11, 17)
        event = {"ticker":"ITUB4","type":"JCP","value":0.5,"approved":today,"payment":dt.date(2026,11,25), "data_com":today, "source":"https://dadosb3.com/"}
        old = dict(event, approved=dt.date(2025,1,1), payment=dt.date(2025,1,15))
        self.assertEqual(gen.choose_events([old, event], today), [event])

    def test_flash_briefing_format(self):
        now = dt.date(2026, 11, 17)
        q = {a["ticker"]: {"price": 30.12, "change": -1.2, "date": now} for a in gen.ASSETS}
        voice = gen.compose(gen.ASSETS, q, [], [], now, [])
        self.assertLess(len(voice), 4500)
        self.assertIn("ITUB4", voice)
        self.assertIn("queda de 1,20 por cento", voice)
        self.assertIn("não confirma que você", voice) if "Dividendos" in voice else None

    def test_missing_quotes_never_fabricated(self):
        voice = gen.compose(gen.ASSETS, {}, [], [], dt.date(2026,11,17), [])
        self.assertIn("Não foi possível atualizar as cotações", voice)
        self.assertNotIn("30 reais", voice)


if __name__ == "__main__":
    unittest.main()
