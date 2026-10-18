"""Synthetic-only financial replay checks. No real saved path is consumed."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_first_period_incumbent_cash_flow_independent_readback_20261003 as reader
from scripts import ndx_first_period_incumbent_cash_flow_paths_20261003 as fixture_producer
from backtest.ndx_incumbent_cash_flow_research import simulate_incumbent_cash_flow
from test_ndx_first_period_incumbent_cash_flow_paths_20261003 import fixture


def documents():
    inputs, nominal, candidates, refs = fixture()
    nominal = deepcopy(nominal)
    # Extra historical dates are legitimate outside the mechanically scoped window.
    nominal['original_fixed_schedule']['calendar'].insert(0, '2023-03-30')
    args_nominal = deepcopy(nominal)
    args_nominal['original_fixed_schedule']['calendar'] = args_nominal['original_fixed_schedule']['calendar'][1:]
    account = fixture_producer.assemble(inputs, args_nominal, candidates, refs, simulate_incumbent_cash_flow)
    account['schema'] = 'FIRST_PERIOD_INCUMBENT_TWO_PATHS_EIGHT_SCENARIOS_V2'
    # The new producer preserves the full nominal calendar in metadata.
    account['parent_nominal_metadata']['original_fixed_schedule']['calendar'] = nominal['original_fixed_schedule']['calendar']
    refs.update(input_publication={'path':'input-pub.json','sha256':'b'*64}, candidate_publication={'path':'candidate-pub.json','sha256':'c'*64})
    oldraw=Path(fixture_producer.__file__).read_bytes()
    refs.update(prior_source=dict(path='old-source.py',sha256=reader.sha(oldraw)),prior_started=dict(path='old-started.json',sha256='d'*64),prior_failure=dict(path='old-failure.json',sha256='e'*64))
    account['input_references'] = deepcopy(refs)
    account['source_hashes'] = {r['path']:r['sha256'] for r in refs.values()}
    ipub = dict(input_reference=refs['inputs'], source_hashes=inputs['source_hashes'])
    candidates['source_hashes'] = {}
    cpub = dict(account_reference=refs['candidates'], source_hashes={}, status='PUBLISHED_CONDITIONAL_PRICE_ONLY_PATHS')
    docs = dict(zip([refs[k]['path'] for k in ('inputs','nominal','candidates','input_publication','candidate_publication')], [inputs,nominal,candidates,ipub,cpub]))
    oldsources={r['path']:r['sha256'] for role,r in refs.items() if not role.startswith('prior_')}
    oldsources[refs['prior_source']['path']]=refs['prior_source']['sha256']
    docs.update({'old-source.py':oldraw,'old-started.json':dict(source_hashes=oldsources,retry_allowed=False),'old-failure.json':dict(error='Exact original107 calendar',retry_allowed=False,status='FAILED_DO_NOT_CONSUME')})
    prior=reader.prior_evidence(refs,docs)
    account.update(prior_attempt_evidence=deepcopy(prior),prior_attempt_pre_dispatch_failure_only=True)
    ar = {'path' :'new-accounts.json','sha256':'f'*64}
    publication = dict(schema='FIRST_PERIOD_INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V2',status='PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS', account_reference=ar,source_hashes=deepcopy(account['source_hashes']),**dict.fromkeys(reader.FALSE,False))
    started = dict(source_hashes=deepcopy(account['source_hashes']), retry_allowed=False)
    publication.update(prior_attempt_evidence=deepcopy(prior),prior_attempt_pre_dispatch_failure_only=True)
    started['prior_attempt_evidence']=deepcopy(prior)
    return dict(account=account, publication=publication, started=started, refs=refs, docs=docs, account_reference=ar)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = documents()

    def test_all_two_paths_212_days_12_plans_and_eight_mappings(self):
        before = deepcopy(self.saved)
        counts = reader.inspect_saved(**self.saved)
        self.assertEqual(counts['paths'],2)
        self.assertEqual(counts['daily'],212)
        self.assertEqual(counts['decisions'],12)
        self.assertEqual(counts['mappings'],8)
        self.assertEqual(counts['quote_references'],2*213*8)
        self.assertEqual(self.saved,before)

    def test_premature_cash_twr_risk_bool_and_initial_shares_rejected(self):
        for mode in ('advance-flow','twr','risk-bool','shares'):
            args = deepcopy(self.saved)
            path = args['account']['paths'][0]
            if mode == 'advance-flow':path['account']['decisions'][0]['future_open_flow_included_in_plan'] = True
            elif mode == 'twr':path['account']['daily'][0]['cumulative_twr']['numerator'] = '999'
            elif mode == 'risk-bool':path['account']['daily'][0]['risk']['checks']['MAX_SINGLE_WEIGHT'] = 1
            else:path['prepared']['core_inputs']['initial']['holdings']['A'] = 1
            with self.subTest(mode=mode), self.assertRaises(AssertionError):reader.inspect_saved(**args)

    def test_candidate_mapping_fee_and_source_quote_tamper(self):
        for mode in ('mapping','flow','quote'):
            args = deepcopy(self.saved)
            if mode == 'mapping':args['account']['scenario_mappings'][0]['candidate_account_reference']['json_pointer']='/rows/1'
            elif mode == 'flow':args['docs'][args['refs']['candidates']['path']]['rows'][0]['accounting_inputs']['sessions'][1]['cash_injection_usd']='1'
            else:args['account']['paths'][0]['prepared']['quote_evidence'][0]['quotes']['A']['literal']='11.0'
            with self.subTest(mode=mode), self.assertRaises(AssertionError):reader.inspect_saved(**args)

    def test_prior_failure_evidence_not_promoted_to_runtime_trace(self):
        for mode in ('trace','failure','source'):
            args=deepcopy(self.saved)
            if mode=='trace':args['account']['prior_attempt_evidence']['prior_runtime_execution_trace_available']=True
            elif mode=='failure':args['docs']['old-failure.json']['error']='Other failure'
            else:args['docs']['old-source.py']+=b'\n# drift'
            with self.subTest(mode=mode),self.assertRaises(AssertionError):reader.inspect_saved(**args)

    def test_pending_before_io(self):
        with patch.object(reader,'PINS',{'accounts.json':None,'publication.json':None}), patch.object(Path,'read_bytes',side_effect=AssertionError('No actual read')):
            with self.assertRaisesRegex(AssertionError,'Future actual anchors'):
                reader.readback(execute=True)


if __name__=='__main__':
    unittest.main()
