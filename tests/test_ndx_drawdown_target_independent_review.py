from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_drawdown_lane_target_materialization_research as core
import test_ndx_drawdown_lane_target_materialization_research as fixtures


class IndependentReview(unittest.TestCase):
    def test_sealed_lane_and_import_endpoints_are_drawdown_only(self):
        sources={};lane=core.read(core.HARD_LANE,sources)
        self.assertEqual(tuple(d['lanes']['DRAWDOWN'][0]['job_id'] for d in lane['decisions']),core.JOBS)
        for decision in lane['decisions']:
            self.assertEqual({r['ticker'] for r in decision['lanes']['DRAWDOWN'][0]['selected'].values()}, {'BKR','CDNS','ENPH','FTNT'})
        for index,ref,auditref in [(0,core.HARD_FIRST,core.HARD_AUDIT),(5,core.HARD_LAST,core.HARD_LAST_AUDIT)]:
            wrapper=core.read(ref,sources);audit=core.read(auditref,sources)
            self.assertEqual(wrapper['job_id'],core.JOBS[index])
            self.assertEqual(wrapper['result']['refit']['previous_target_weights'],{})
            self.assertEqual(wrapper['result']['refit']['effective_anchor_strength'],0)
            matches=[row for row in audit['details'] if row['job_id']==core.JOBS[index]]
            self.assertEqual(len(matches),1);self.assertEqual(matches[0]['result_reference'],ref)
        with patch.object(core,'prepare_plan') as prepare:
            with self.assertRaises(ValueError):
                core.run_step(plan_reference={},output=core.OUTPUT.with_name('bad_tail_lane_targets_20260923_v1'),execution_date=core.DATES[0])
            prepare.assert_not_called()

    def test_imported_last_prior_is_not_rewritten_to_lane_prior(self):
        _,state=fixtures.DrawdownTargetTests().fixture()
        state['last_refit']['previous_target_weights']={}
        modified=deepcopy(state['last_refit']);modified['previous_target_weights']={'sid-a':.6,'sid-b':.4}
        with self.assertRaisesRegex(ValueError,'original numerical provenance'):
            core.validate_fit(state,5,modified,{'sid-a':.6,'sid-b':.4})
        binding=core.lane_binding(state,5,{'sid-a':.6,'sid-b':.4})
        self.assertEqual(binding['fit_actual_previous_target_weights'],{})
        self.assertEqual(binding['lane_previous_target_weights'],{'sid-a':.6,'sid-b':.4})
        self.assertFalse(binding['fit_uses_lane_previous_target'])

    def test_exit_sid_current_risk_and_issuer_cannot_be_omitted_or_replaced(self):
        _,state=fixtures.DrawdownTargetTests().fixture()
        exit_row=dict(ticker='EXIT',issuer_id='issuer-exit',risk_chain='current-chain')
        state['periods'][0]['selected']['sid-exit']=dict(exit_row,risk_chain='old-chain')
        state['periods'][1]['universe_by_sid']['sid-exit']=exit_row
        previous={'sid-a':.4,'sid-b':.4,'sid-exit':.2}
        self.assertEqual(core.lane_binding(state,1,previous)['lane_risk_chains_by_security']['sid-exit'],'current-chain')
        for key,value in [('issuer_id','wrong'),('ticker','WRONG'),('risk_chain','')]:
            changed=deepcopy(state);changed['periods'][1]['universe_by_sid']['sid-exit'][key]=value
            with self.assertRaises(ValueError):core.lane_binding(changed,1,previous)

    def test_orphan_during_fit_blocks_finalization_after_raw_saved(self):
        fixture=fixtures.DrawdownTargetTests();reference,state=fixture.fixture()
        with tempfile.TemporaryDirectory() as folder,fixture.patches(state,folder):
            first=core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],execute=True)
            def fitted(*args):
                (Path(folder)/core.DATES[1]/'orphan.json').write_text('{}')
                return state['first_refit']
            with patch.object(core,'fit_once',side_effect=fitted):
                with self.assertRaises(ValueError):
                    core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[1],execute=True,
                                  completed_finalizations=[first['final_reference']])
            self.assertTrue((Path(folder)/core.DATES[1]/'raw.json').exists())

    def test_fit_preserves_entire_previous_weights_including_exit(self):
        fixture=fixtures.DrawdownTargetTests();reference,state=fixture.fixture()
        exit_row=dict(ticker='EXIT',issuer_id='issuer-exit',risk_chain='exit-chain')
        state['first_refit']['targets']['sid-exit']=dict(ticker='EXIT',issuer_id='issuer-exit',target_weight=.2)
        state['periods'][0]['selected']['sid-exit']=exit_row
        for period in state['periods']:period['universe_by_sid']['sid-exit']=exit_row
        with tempfile.TemporaryDirectory() as folder,fixture.patches(state,folder),patch.object(core,'fit_once',return_value=state['first_refit']) as fit:
            first=core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],execute=True)
            core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[1],execute=True,
                          completed_finalizations=[first['final_reference']])
            self.assertEqual(fit.call_args.args[2],{'sid-a':.6,'sid-b':.4,'sid-exit':.2})


if __name__=='__main__':unittest.main()

