from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
import unittest
import hashlib
import json
import tempfile
from pathlib import Path
from scripts.return_priority_current_rebased_training import prepare_saved, ROOT
from scripts.return_priority_current_rebased_training import prepare


def fixture():
    days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(253)]
    row = dict(ticker='A', security_id='a', issuer_id='issuer-a', status='READY_CONDITIONAL',
        identity_reviewed=True, coordinate_reviewed=True, blockers=[],
        identity_source_references=['identity'], coordinate_source_references=['coordinate'],
        training_source='raw', raw_close=['100']*253,
        training_rule='UNCHANGED_WHOLE_QUOTE_CLOSE', price_coordinate_factors=[],
        true_share_events=[], decision_nominal_close='100')
    return dict(decision_date=days[-1], coordinate_asof_date=days[-1], training_dates=days,
        members=['A'], candidates=[row], source_hashes={k:'a'*64 for k in ['identity','coordinate','raw','admission']},
        admission=dict(decision_date=days[-1], status='REVIEWED_CONDITIONAL', members=['A'],
            training_exclusions={}, source_references=['admission']))


class CurrentRebasedCompilerTests(unittest.TestCase):
    def test_reverse_units_removed_but_distribution_price_loss_retained(self):
        data=fixture(); row=data['candidates'][0]; day=data['training_dates'][21]
        row.update(training_rule='RESTORED_PARENT_PRICE_ONLY', raw_close=['100']*21+['180']*232,
            decision_nominal_close='180', true_share_events=[dict(date=day,ratio='1/2',source_references=['coordinate'])])
        before=deepcopy(data); result=prepare(data); args=result['search_arguments']
        self.assertEqual(args['training_scenarios'][0]['a'],'9/10')
        self.assertEqual(args['training_scenarios'][1]['a'],'1')
        self.assertEqual(args['scenario_dates'],data['training_dates'][21::21])
        self.assertEqual(len(args['training_scenarios']),12)
        self.assertEqual(data,before)

    def test_quote_split_not_double_counted_and_nominal_cost_separate(self):
        data=fixture(); row=data['candidates'][0]
        row['true_share_events']=[dict(date=data['training_dates'][21],ratio='10',source_references=['coordinate'])]
        args=prepare(data)['search_arguments']
        self.assertTrue(all(s['a']=='1' for s in args['training_scenarios']))
        row['decision_nominal_close']='200'
        with self.assertRaisesRegex(ValueError,'DECISION_COST_COORDINATE_MISMATCH'):prepare(data)
        row['decision_nominal_close']='100'
        row['price_coordinate_factors']=[dict(date=data['training_dates'][21],factor='2',source_references=['coordinate'])]
        row['training_rule']='RESTORED_PARENT_PRICE_ONLY'; row['true_share_events']=[]
        self.assertEqual(prepare(data)['search_arguments']['training_scenarios'][0]['a'],'1/2')

    def test_missing_history_preserves_domain_and_short_history_requires_admission(self):
        data=fixture(); row=deepcopy(data['candidates'][0]); row.update(ticker='B',security_id='b',issuer_id='issuer-b')
        data['candidates'].append(row); data['members'].append('B'); data['admission']['members'].append('B')
        row['raw_close'][10]=None
        result=prepare(data)
        self.assertEqual(result['coverage_denominator'],2); self.assertIsNone(result['search_arguments'])
        self.assertEqual(result['blocked_tickers'],['B'])
        row.update(status='EXCLUDED_TRAINING_RULE')
        with self.assertRaisesRegex(ValueError,'EXCLUSION_NOT_ADMITTED'):prepare(data)
        data['admission']['training_exclusions']['B']=dict(reason='INSUFFICIENT_253_SESSION_PREDECISION_HISTORY',
            known_asof=data['decision_date'],source_references=['admission'])
        result=prepare(data)
        self.assertEqual(result['coverage_denominator'],2);self.assertEqual(set(result['search_arguments']['prices']),{'a'})

    def test_saved_output_pins_are_relative_and_outside_sources_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            folder=Path(directory); data=fixture()
            for name in list(data['source_hashes']):
                source=folder/name; source.write_text(name,encoding='utf-8')
                relative=source.relative_to(ROOT).as_posix()
                def replace_values(value):
                    if isinstance(value,dict):return {k:replace_values(v) for k,v in value.items()}
                    if isinstance(value,list):return [replace_values(v) for v in value]
                    return relative if value==name else value
                data=replace_values(data)
                del data['source_hashes'][name]
                data['source_hashes'][relative]=hashlib.sha256(source.read_bytes()).hexdigest()
            manifest=folder/'manifest.json';manifest.write_text(json.dumps(data),encoding='utf-8')
            prepared=prepare_saved(manifest,folder/'output')
            result=json.loads(Path(prepared['path']).read_text(encoding='utf-8'))
            self.assertIn(manifest.relative_to(ROOT).as_posix(),result['source_hashes'])
            self.assertIn('scripts/return_priority_current_rebased_training.py',result['source_hashes'])
            self.assertTrue(all(not Path(key).is_absolute() and '\\' not in key for key in result['source_hashes']))
            first=next(iter(data['source_hashes']))
            digest=data['source_hashes'].pop(first)
            data['source_hashes'][str((ROOT/first).resolve())]=digest
            manifest.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'SOURCE_PATH_MUST_BE_REPO_RELATIVE_POSIX'):
                prepare_saved(manifest,folder/'rejected')
            self.assertFalse((folder/'rejected').exists())

    def test_coordinate_events_and_sources_fail_closed(self):
        data=fixture(); row=data['candidates'][0]
        row['identity_source_references']=['absent']
        with self.assertRaisesRegex(ValueError,'UNPINNED'):prepare(data)
        row['identity_source_references']=['identity']
        row['price_coordinate_factors']=[dict(date='2099-01-01',factor='2',source_references=['coordinate'])]
        with self.assertRaisesRegex(ValueError,'UNOBSERVED_COORDINATE_EVENT'):prepare(data)
        row['price_coordinate_factors']=[dict(date=data['decision_date'],factor='2',source_references=['coordinate'])]*2
        with self.assertRaisesRegex(ValueError,'DUPLICATE_COORDINATE_EVENT'):prepare(data)

if __name__=='__main__':unittest.main()
