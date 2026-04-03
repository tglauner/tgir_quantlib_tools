import unittest

import QuantLib as ql

from portfolio import build_sofr_curve, reprice_sofr_calibration_swaps


class SofrCurveTests(unittest.TestCase):
    def test_curve_reprices_2y_5y_and_10y_swaps(self):
        today = ql.Date.todaysDate()
        ql.Settings.instance().evaluationDate = today
        sofr_quotes = [5.0, 5.1, 5.2, 5.3, 5.4]

        curve = build_sofr_curve(today, sofr_quotes)
        repriced = reprice_sofr_calibration_swaps(curve, sofr_quotes)

        self.assertListEqual(repriced["Tenor"].tolist(), ["2Y", "5Y", "10Y"])
        for npv in repriced["NPV"]:
            self.assertAlmostEqual(npv, 0.0, places=10)


if __name__ == "__main__":
    unittest.main()
