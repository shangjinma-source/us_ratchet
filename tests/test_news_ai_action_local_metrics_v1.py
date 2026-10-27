import unittest
from scripts.research.review_news_ai_action_local_v1 import interval_metrics,compare_fills

class MetricsTests(unittest.TestCase):
    def test_initial_peak_is_included(self):
        result=interval_metrics('100',[{'equity':'80'},{'equity':'90'}])
        self.assertEqual(result['maximum_drawdown'],'1/5')
        self.assertEqual(result['interval_return'],'-1/10')

    def test_new_peak_changes_drawdown(self):
        self.assertEqual(interval_metrics('100',[{'equity':'120'},{'equity':'90'}])['maximum_drawdown'],'1/4')

    def test_changed_quantity_distinguished_from_identical_fills(self):
        fill=dict(date='2021-11-08',security_id='A',side='BUY',quantity=2,price='10',fee='0',event='ASSUMED_NEXT_OPEN_FILLED')
        base={'order_log':[fill]};branch={'order_log':[dict(fill,quantity=1)]}
        self.assertEqual(compare_fills(base,base)['changed_fill_key_count'],0)
        result=compare_fills(base,branch)
        self.assertEqual(result['baseline_only_fill_count'],1)
        self.assertEqual(result['branch_only_fill_count'],1)

if __name__=='__main__':unittest.main()
