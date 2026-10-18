import unittest
from scripts.return_priority_exposed_gross_multicurrency_projection import project, prepare
from pathlib import Path


class ProjectionTests(unittest.TestCase):
    def event(self, currency='USD'):
        return dict(account='a', security_id='s', ex_date='2026-07-28', payment_date='2026-08-05', aggregation_currency=currency, aggregation_amount_exact='534437/250000')

    def test_receivable_until_payment_and_no_double_count(self):
        e=self.event();e.update(original_currency='EUR',original_amount_exact='47/25')
        p=project([e],{'a':['2026-07-27','2026-07-28','2026-07-30','2026-08-05']})
        self.assertEqual(p['timeline'][0]['legs']['USD']['gross_accrued_exact'],'0')
        self.assertEqual(p['timeline'][2]['legs']['USD']['theoretical_gross_paid_exact'],'0')
        self.assertEqual(p['timeline'][2]['legs']['USD']['gross_receivable_exact'],'534437/250000')
        self.assertEqual(p['terminal']['a']['legs']['USD']['gross_receivable_exact'],'0')
        self.assertEqual(p['terminal']['a']['legs']['EUR']['gross_accrued_exact'],'0')

    def test_duplicate_and_bad_payment_rejected(self):
        e=self.event()
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):project([e,e],{'a':['2026-07-30']})
        e['payment_date']='2026-07-27'
        with self.assertRaisesRegex(ValueError,'PAYMENT_BEFORE'):project([e],{'a':['2026-07-30']})

    def test_actual_753_readonly(self):
        p=prepare(Path(__file__).resolve().parents[1])
        self.assertEqual(len(p['timeline']),753)
        self.assertEqual(len(p['events']),31)
        self.assertEqual(p['terminal']['original8']['legs']['EUR']['theoretical_gross_paid_exact'],'59/10')
        self.assertEqual(p['terminal']['quantity']['legs']['USD']['gross_accrued_exact'],'4831/200')
        self.assertEqual(p['terminal']['top1']['legs']['USD']['gross_accrued_exact'],'107/8')
        self.assertEqual(len(p['terminal']['original8']['outstanding']),1)


if __name__=='__main__':unittest.main()
