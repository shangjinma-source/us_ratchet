"""Independent ordered objective and full-EOF checks for double selection."""
from copy import deepcopy
import unittest
import test_ndx_double_stream_selection_20261008 as fixtures


class ReviewTests(unittest.TestCase):
    def test_fee_is_secondary_and_whole_generator_is_consumed(self):
        prepared, records, audit = fixtures.fixture(1)
        self.assertGreater(len(records), 1)
        evaluation = records[-1]['raw']['evaluation']
        evaluation.update(total_fee_usd='1', sell_fee_usd='0', buy_fee_usd='1')
        consumed = []

        def stream():
            for index, record in enumerate(records):
                consumed.append(index)
                yield record

        selected = fixtures.pure.select(prepared=prepared, audit=audit, records=stream())
        self.assertEqual(consumed, list(range(len(records))))
        self.assertEqual(selected['rows'][0]['selected'], records[-1])
        fixtures.checker.inspect(prepared=prepared, audit=audit, records=iter(records), selection=selected)
        altered = deepcopy(selected);altered['rows'][0]['selected'] = records[0]
        with self.assertRaises(ValueError):
            fixtures.checker.inspect(prepared=prepared, audit=audit, records=iter(records), selection=altered)

    def test_independent_reader_rejects_truncated_extra_and_wrong_locator(self):
        prepared, records, audit = fixtures.fixture(40)
        selected = fixtures.pure.select(prepared=prepared, audit=audit, records=iter(records))
        for incoming in (records[:-1], records + [records[-1]], records[1:]):
            with self.subTest(length=len(incoming)), self.assertRaises(ValueError):
                fixtures.checker.inspect(prepared=prepared, audit=audit, records=iter(incoming), selection=selected)
        changed = deepcopy(selected)
        changed['rows'][0]['selected']['locator']['synthetic_ordinal'] = 99
        with self.assertRaises(ValueError):
            fixtures.checker.inspect(prepared=prepared, audit=audit, records=iter(records), selection=changed)


if __name__ == '__main__': unittest.main()
