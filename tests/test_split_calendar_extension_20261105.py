from copy import deepcopy
import unittest
from docs.candidates.split_calendar_extension_20261105 import validate_calendar_extension


class Tests(unittest.TestCase):
    def test_append_only_preserves_fixed_history_and_rejects_rewrites(self):
        def session(day):
            return dict(date=day, open=day+'T14:30:00+00:00', close=day+'T21:00:00+00:00')
        pinned = dict(schema='FIXED_EXCHANGE_SESSIONS_V1', exchange='NASDAQ', sessions=[session('2026-11-19'),session('2026-11-20')])
        current = deepcopy(pinned)
        current['sessions'].append(session('2026-11-23'))
        frozen = deepcopy((pinned,current))
        self.assertEqual(validate_calendar_extension(pinned=pinned,current=current)['added_session_count'],1)
        self.assertEqual(validate_calendar_extension(pinned=pinned,current=pinned)['added_session_count'],0)
        for mode in ('rewrite','remove','prepend','duplicate','wrong_day','header'):
            with self.subTest(mode=mode):
                changed = deepcopy(current)
                if mode == 'rewrite': changed['sessions'][0]['open']='2026-11-19T15:00:00+00:00'
                if mode == 'remove': changed['sessions'].pop(0)
                if mode == 'prepend': changed['sessions'].insert(0,session('2026-11-18'))
                if mode == 'duplicate': changed['sessions'].append(session('2026-11-23'))
                if mode == 'wrong_day': changed['sessions'][-1]['close']='2026-11-24T21:00:00+00:00'
                if mode == 'header': changed['exchange']='NYSE'
                with self.assertRaises(ValueError): validate_calendar_extension(pinned=pinned,current=changed)
        self.assertEqual((pinned,current),frozen)


if __name__ == '__main__': unittest.main()
