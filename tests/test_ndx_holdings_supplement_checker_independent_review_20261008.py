"""Independent table EOF and absent-risk interpretation rejection tests."""
from copy import deepcopy
import unittest
from backtest import ndx_multidecision_holdings_supplement_research as producer
from backtest import ndx_multidecision_holdings_supplement_inspection_research as checker
import test_ndx_multidecision_holdings_supplement_research as fixtures


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arguments=fixtures.fixture();cls.saved=producer.build_supplement(**cls.arguments)

    def test_all_six_table_eof_boundaries(self):
        for index in range(6):
            for attack in ('extra','missing'):
                with self.subTest(table=index,attack=attack):
                    value=deepcopy(self.saved);rows=value['tables'][index]['rows']
                    if attack=='extra':rows.append(deepcopy(rows[-1]))
                    else:rows.pop()
                    with self.assertRaises(ValueError):checker.inspect_supplement(supplement=value,**self.arguments)

    def test_missing_risk_or_empty_holdings_cannot_become_evidence(self):
        for attack in ('riskzero','empty_sid','internal_as_real','risk_status'):
            with self.subTest(attack=attack):
                value=deepcopy(self.saved)
                if attack=='riskzero':value['tables'][4]['rows'][0][7]='{"risk":0}'
                elif attack=='empty_sid':value['tables'][3]['rows'][0][6]='invented-position'
                elif attack=='internal_as_real':value['tables'][3]['rows'][1][7]=value['tables'][3]['rows'][1][9]
                else:value['tables'][4]['rows'][0][6]='SAVED_RISK_UNCHANGED'
                with self.assertRaises(ValueError):checker.inspect_supplement(supplement=value,**self.arguments)


if __name__=='__main__':unittest.main()
