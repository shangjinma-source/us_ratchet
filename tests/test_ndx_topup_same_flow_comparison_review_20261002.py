from copy import deepcopy
from decimal import Decimal, Context, Inexact, localcontext
from fractions import Fraction as F
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import importlib.util
from backtest import ndx_topup_same_flow_comparison_research as m
from test_ndx_topup_same_flow_comparison_research import fixture

class IndependentReview(unittest.TestCase):
    def test_annual_independent_lnexp_initial_one_dd_and_policy(self):
        args=fixture()
        with localcontext() as c:
            c.prec=2; c.traps[Inexact]=True
            result=m.compare_same_flow_paths(**args)
        for row in result['rows']:
            for role,terminal,dd in [('candidate',F(6,5),F(1,10)),('same_flow_incumbent',F(11,10),F(0))]:
                metrics=row['metrics'][role]
                self.assertEqual(metrics['maximum_drawdown'],{'numerator':str(dd.numerator),'denominator':str(dd.denominator)})
                with localcontext(Context(prec=110)):
                    expected=((Decimal(terminal.numerator)/Decimal(terminal.denominator)).ln()*Decimal(126)).exp()-1
                    actual=Decimal(metrics['annualized_return_diagnostic_decimal'])
                    self.assertLess(abs(actual-expected)/max(Decimal(1),abs(expected)),Decimal('1e-76'))
                self.assertEqual(metrics['wealth'][0]['normalized_wealth'],{'numerator':'1','denominator':'1'})
            self.assertFalse(row['formal_dual_benchmark_admission']); self.assertFalse(row['decision_information_sets_equivalent'])
            self.assertIn('EXECUTION_OPEN',row['policy_asymmetry']['candidate_quantity_information'])
            self.assertIn('CLOSE_FROZEN',row['policy_asymmetry']['incumbent_quantity_information'])

    def test_forty_mapping_last_row_and_zero_slot_full_state(self):
        for kind in ('last_reference','last_mapping','zero_key','fee','timing','negative_wealth'):
            a=fixture()
            if kind=='last_reference': a['incumbent_accounts']['scenario_mappings'][-1]['input_reference']['json_pointer']='/rows/0'
            elif kind=='last_mapping': a['incumbent_accounts']['scenario_mappings'][-1]['scenario_id']='0'
            elif kind=='zero_key': a['paired_accounts']['rows'][0]['paths']['candidate']['accounting_inputs']['initial']['holdings']['Z']=0
            elif kind=='fee': a['incumbent_accounts']['paths'][-1]['account']['transaction_cost_bps']='11'
            elif kind=='timing': a['incumbent_accounts']['paths'][-1]['account']['cash_event_timing']='BEFORE_OLD_OPEN_MARK'
            else: a['paired_accounts']['rows'][-1]['paths']['candidate']['account']['rows'][0]['cumulative_twr']={'numerator':'-1','denominator':'1'}
            with self.subTest(kind=kind),self.assertRaises(ValueError): m.compare_same_flow_paths(**a)

    def test_identical_returns_ignores_terminal_dollars_and_preserves_evidence(self):
        a=fixture()
        for row in a['paired_accounts']['rows']:
            account=row['paths']['candidate']['account']
            for i,d in enumerate(account['rows']): d['cumulative_twr']={'numerator':str(i),'denominator':'10'}
            account['chained_twr']={'numerator':'1','denominator':'10'}
        saved=deepcopy(a); r=m.compare_same_flow_paths(**a)
        self.assertEqual(a,saved)
        for row in r['rows']:
            self.assertEqual(row['candidate_minus_incumbent']['cumulative_return'],{'numerator':'0','denominator':'1'})
            self.assertEqual(Decimal(row['candidate_minus_incumbent']['annualized_return_diagnostic_decimal']),0)
            self.assertEqual(row['input_row']['gaps'],['not resolved'])
            self.assertEqual(row['observations']['candidate'][0]['source_row']['close_equity_usd'],'12345678')

    def test_wrapper_failed_parent_and_existing_output(self):
        path=Path(__file__).resolve().parents[1]/'scripts/ndx_topup_same_flow_comparison_20261002.py'
        spec=importlib.util.spec_from_file_location('review_sameflow_wrapper',path); w=importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(w,'OUTPUT',Path(folder)),patch.object(w,'load_compare') as compare:
                with self.assertRaisesRegex(ValueError,'namespace'): w.run()
                compare.assert_not_called()
            refs={}; docs={}
            for prefix,schema,status in [('paired','OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1','PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS'),('incumbent','INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V1','PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS')]:
                d=Path(folder)/prefix; d.mkdir()
                for name in ('started.json','accounts.json','publication.json'): (d/name).write_text('{}')
                refs[prefix+'_accounts']={'path':str(d/'accounts.json'),'sha256':'a'*64}
                refs[prefix+'_publication']={'path':str(d/'publication.json'),'sha256':'b'*64}
                flags=dict.fromkeys(('orders_executed','point_in_time_verified','promotion_allowed','full_transitive_source_closure_reverified'),False)
                docs[prefix+'_accounts']={'source_hashes':{},**flags}
                docs[prefix+'_publication']={'schema':schema,'status':status,'account_reference':refs[prefix+'_accounts'],'source_hashes':{},**flags}
            w.validate_publications(docs,refs)
            (Path(folder)/'incumbent/failure.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'namespace'): w.validate_publications(docs,refs)
            (Path(folder)/'incumbent/failure.json').unlink()
            docs['paired_publication']['account_reference']['sha256']='f'*64
            # Do not share the mutable reference in this mutation oracle.
            refs['paired_accounts']={'path':str(Path(folder)/'paired/accounts.json'),'sha256':'a'*64}
            with self.assertRaisesRegex(ValueError,'publication'): w.validate_publications(docs,refs)

if __name__=='__main__': unittest.main()
