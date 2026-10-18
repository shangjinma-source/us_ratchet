from copy import deepcopy
import itertools
import unittest
from backtest import ndx_multidecision_training_inputs_research as m
from test_ndx_dated_training_panel_research import fixture as source_fixture


def fixture():
    original = source_fixture(); s = original['channels_document']
    # A small full supplied domain includes two classes of the same issuer.
    s['rows'] = s['rows'][:4]
    s.update(security_count=4, issuer_count=3, conditional_numeric_channel_count=4)
    c = s['calendar253']; first = {}
    for i,d in enumerate(c):first.setdefault(d[:7], i)
    choices = [i for i in first.values() if i >= 127]
    contract = dict(schema=m.CONTRACT_SCHEMA,status='DRAFT_NOT_REGISTERED',rule=m.RULE,
        rule_reference=dict(path='historical-rule.yaml',sha256='d'*64),
        decisions=[dict(decision_date=c[i-1],execution_date=c[i]) for i in choices],
        expected_decision_count=len(choices),selection_contract_reference=None,search_budget_reference=None)
    return dict(channels_document=s,channels_reference=original['channels_reference'],
        expected_security_inventory=[{k:r['coordinate'][k] for k in ('security_id','ticker','issuer_id')} for r in s['rows']],
        decision_path_contract=contract,decision_path_reference=dict(path='explicit-draft.json',sha256='e'*64),
        fit_contract=dict(parameters=deepcopy(m.PARAMETERS),weight_specifications=deepcopy(m.SPECS)))


class PreparationTests(unittest.TestCase):
    def test_causal_slices_prior_denominators_and_preservation(self):
        a=fixture(); before=deepcopy(a); out=m.prepare_multidecision_inputs(**a)
        self.assertEqual(a,before)
        self.assertEqual([r['combination_count'] for r in out['all_k_issuer_unique_combination_counts']],[4,5,2])
        inv=a['expected_security_inventory']
        for k, row in enumerate(out['all_k_issuer_unique_combination_counts'],1):
            oracle=sum(len({v['issuer_id'] for v in combo})==k for combo in itertools.combinations(inv,k))
            self.assertEqual(row['combination_count'],oracle)
        c=a['channels_document']['calendar253']
        for n,p in enumerate(out['periods']):
            j=c.index(p['cutoff']);self.assertEqual(p['returns']['index'],[x+'T00:00:00' for x in c[j-125:j+1]])
            self.assertEqual(p['training_price_predecessor'],c[j-126]);self.assertEqual(len(p['returns']['data']),126)
            self.assertIsNone(p['numerical_task_id']);self.assertFalse(p['task_materialization_allowed'])
            self.assertEqual(p['prior_dependency']['dependency_resolved'],n==0)
            self.assertEqual(p['prior_dependency']['previous_period_index'],None if n==0 else n-1)
        self.assertEqual(out['preserved_evidence_sidecars'],a['channels_document']['preserved_evidence_sidecars'])
        self.assertEqual(len(out['original_provenance_and_missing']),101)
        self.assertTrue(all(out[k] is False for k in m.FLAGS))

    def test_missing_contract_clock_and_denominator(self):
        changes=[lambda a:a.update(decision_path_contract=None),
            lambda a:a['decision_path_contract'].update(expected_decision_count=True),
            lambda a:a['decision_path_contract']['decisions'].reverse(),
            lambda a:a['decision_path_contract']['decisions'].append(deepcopy(a['decision_path_contract']['decisions'][0])),
            lambda a:a['decision_path_contract']['decisions'][0].update(decision_date='2026-03-20',execution_date='2026-03-23'),
            lambda a:a['decision_path_contract']['decisions'][0].update(execution_date='2026-00-01'),
            lambda a:a['decision_path_contract'].update(prior={})]
        for change in changes:
            a=fixture();change(a)
            with self.subTest(change=change),self.assertRaises(ValueError):m.prepare_multidecision_inputs(**a)

    def test_exact_returns_and_inventory_fail_closed(self):
        changes=[lambda a:a['channels_document']['rows'][0]['channel']['return_rows'][140].update(split_only_return_float=True),
            lambda a:a['channels_document']['rows'][0]['channel']['return_rows'][140].update(previous_session='2020-01-01'),
            lambda a:a['channels_document']['rows'][0]['channel']['calendar'].pop(130),
            lambda a:a['expected_security_inventory'].pop(),
            lambda a:a['channels_document'].update(point_in_time_verified=0),
            lambda a:a['channels_document']['rows'][0]['coordinate'].update(risk_chain=None)]
        for change in changes:
            a=fixture();change(a)
            for row in a['channels_document']['rows']:
                ch=row['channel'];ch['training_returns_sha256']=m.digest(ch['training_returns']);ch['evaluation_returns_sha256']=m.digest(ch['evaluation_returns'])
            with self.subTest(change=change),self.assertRaises(ValueError):m.prepare_multidecision_inputs(**a)

    def test_mdv_and_post_cutoff_values_do_not_change_first_matrix(self):
        a=fixture();before=m.prepare_multidecision_inputs(**a)
        a['channels_document']['rows'][0]['coordinate']['median_dollar_volume_usd']=1e99
        ch=a['channels_document']['rows'][0]['channel'];ch['return_rows'][-1].update(split_only_return_exact='1/2',split_only_return_float=.5)
        ch['evaluation_returns_sha256']=m.digest(ch['evaluation_returns'])
        after=m.prepare_multidecision_inputs(**a)
        self.assertEqual(before['periods'][0]['training_frame_sha256'],after['periods'][0]['training_frame_sha256'])
        self.assertNotIn('median_dollar_volume_usd',after['periods'][0]['selected_inventory_by_security']['S000'])
        self.assertFalse(after['historical_liquidity_qualified'])
        self.assertIn('MISSING_SEARCH_BUDGET_REFERENCE',after['research_blockers'])

if __name__=='__main__':unittest.main()
