"""Boundary checks for the conditional publication-date research helper."""

import unittest

from scripts.research.news_date_only_bound_v1 import bound


class DateBoundTests(unittest.TestCase):
    def call(
        self,
        publication_date: str = "2023-11-21",
        next_open: str = "2023-11-22T14:30:00Z",
        processing_seconds: int = 120,
        confirmed: bool = True,
    ) -> dict[str, object]:
        return bound(
            publication_date,
            next_open,
            processing_seconds,
            confirmed_publication_date_label=confirmed,
        )

    def test_latest_civil_offset_and_nvda_window(self) -> None:
        result = self.call()
        self.assertEqual(result["upper_bound_utc"], "2023-11-22T12:00:00+00:00")
        self.assertEqual(
            result["eligible_upper_bound_utc"], "2023-11-22T12:02:00+00:00"
        )
        self.assertTrue(result["executable"])
        self.assertEqual(
            result["quality"], "DATE_ONLY_CONSERVATIVE_GLOBAL_BOUND_CONDITIONAL"
        )

    def test_equal_open_rejected(self) -> None:
        result = self.call(next_open="2023-11-22T12:02:00Z")
        self.assertFalse(result["executable"])

    def test_same_day_open_not_borrowed(self) -> None:
        result = self.call(next_open="2023-11-21T09:30:00-05:00")
        self.assertFalse(result["executable"])

    def test_missing_and_noncanonical_dates(self) -> None:
        for value in (None, "", "20231121", "2023-11-21T00:00:00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.call(publication_date=value)
        with self.assertRaises(ValueError):
            self.call(confirmed=False)

    def test_naive_clock_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.call(next_open="2023-11-22T14:30:00")

    def test_negative_boolean_fractional_delay_rejected(self) -> None:
        for value in (-1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.call(processing_seconds=value)


if __name__ == "__main__":
    unittest.main()
