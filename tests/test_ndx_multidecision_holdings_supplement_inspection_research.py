from copy import deepcopy
import unittest
from unittest.mock import patch

from backtest import ndx_multidecision_holdings_supplement_research as producer
from backtest import ndx_multidecision_holdings_supplement_inspection_research as inspector
import test_ndx_multidecision_holdings_supplement_research as fixtures


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arguments = fixtures.fixture()
        cls.saved = producer.build_supplement(**cls.arguments)

    def test_full_scope_without_producer_helpers(self):
        with patch.object(producer,'build_supplement',side_effect=AssertionError('producer')), patch.object(producer,'text',side_effect=AssertionError('helper')):
            report = inspector.inspect_supplement(supplement=self.saved, **self.arguments)
        self.assertEqual(report['table_count'],6)
        self.assertEqual(report['counts']['daily_rows'],2880)
        self.assertEqual(report['checked_cell_count'],sum(len(row) for table in self.saved['tables'] for row in table['rows']))

    def test_changed_cells_missing_tail_and_authority_rejected(self):
        for attack in ('identity','target','day','holding','risk','blocked','missing','extra','authority','raw','gap','pointer'):
            with self.subTest(attack=attack):
                value = deepcopy(self.saved)
                tables = value['tables']
                if attack == 'identity': tables[0]['rows'][0][4]='WRONG'
                elif attack == 'target': tables[1]['rows'][0][7]='0'
                elif attack == 'day': tables[2]['rows'][-1][6]='{}'
                elif attack == 'holding': tables[3]['rows'][-1][10]='999'
                elif attack == 'risk': tables[4]['rows'][0][7]='0'
                elif attack == 'blocked': tables[5]['rows'][0][5]='[]'
                elif attack == 'missing': tables[3]['rows'].pop()
                elif attack == 'extra': tables[5]['rows'].append(tables[5]['rows'][0])
                elif attack == 'authority': value['risk_recomputed']=0
                elif attack == 'raw': value['original_raw_bundles_preserved']['candidate'][8]['document']['result']['daily'][-1]['session']='changed'
                elif attack == 'gap': value['remaining_gaps'].pop()
                else: tables[3]['rows'][-1][-1]='{}'
                with self.assertRaises(ValueError): inspector.inspect_supplement(supplement=value,**self.arguments)


if __name__ == '__main__': unittest.main()
