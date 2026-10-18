import unittest
from scripts import ndx_current_tsm_raw_readback_20260919 as m


class Tests(unittest.TestCase):
    def info(self):
        dates=['2026-09-10','2026-09-11','2026-09-14','2026-09-15','2026-09-16','2026-09-17','2026-09-18']
        return dict(days=dates,quotes=dict(open=[100.]*7,close=[101.]*7))

    def test_completed_new_day_does_not_upgrade_fixed_target(self):
        info=self.info();r=m.summarize(info,'2026-09-19',info['days'][:-1])
        self.assertEqual(r['target_completed_calendar'][-1],'2026-09-17')
        self.assertEqual(r['receipt_completed_calendar'][-1],'2026-09-18')
        self.assertEqual(r['excluded_after_fixed_target'],['2026-09-18'])
        self.assertEqual(r['missing_last_five'],[])

    def test_null_bool_or_receipt_bar_not_counted_as_valid_target(self):
        for value in (None,True,float('nan')):
            info=self.info();info['quotes']['open'][-2]=value
            r=m.summarize(info,'2026-09-19',info['days'][:-1])
            self.assertEqual(r['missing_last_five'],['2026-09-17'])
            self.assertFalse(r['target_cutoff_covered'])
        info=self.info();r=m.summarize(info,'2026-09-17',info['days'][:-1])
        self.assertEqual(r['missing_last_five'],['2026-09-17'])


if __name__=='__main__':unittest.main()
