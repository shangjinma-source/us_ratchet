from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_dated_per_task_continuous_independent_readback_20261003 as m
from test_ndx_dated_per_task_continuous_independent_readback_20261003 import fixture
from test_ndx_dated_per_task_continuous_20261003 import core as producer,numeric


class Tests(unittest.TestCase):
    def test_entry_split_is_not_post_entry_quantity_multiplier(self):
        tid,d,r=fixture();inp=d['inputs']['inputs'];a=inp['candidate'];sid=a['original_security_order'][0]
        e=a['split_evidence_preserved'][sid][0]['event'];old=e['session'];e['session']=inp['calendar'][1]
        for event in a['corporate_actions']:
            if event['security_id']==sid:event['session']=inp['calendar'][1]
        args=producer.project_track(inp,'candidate',r['inputs']);track=numeric.diagnose_continuous_weights(**args)
        result=m.inspect_candidate(track,inp,r['inputs']);self.assertEqual(result['split_event_count'],2)
        # An event moved to entry occurs while holdings are zero; no x25.
        self.assertEqual(track['path'][1]['security_rows'][0]['fractional_quantity'],{'numerator':'1','denominator':'200'})
        bad=deepcopy(track);bad['path'][1]['security_rows'][0]['fractional_quantity']['numerator']='25'
        with self.assertRaises(ValueError):m.inspect_candidate(bad,inp,r['inputs'])

    def test_complete_expected_track_and_external_links(self):
        tid,d,r=fixture(True)
        for mutate in (
            lambda x:x['candidate'].__setitem__('max_drawdown_exact',{'numerator':'0','denominator':'1'}),
            lambda x:x['candidate']['source_references_preserved']['inputs'].__setitem__('json_pointer','/inputs/incumbent'),
            lambda x:x['candidate']['path'][0].__setitem__('normalized_value',{'numerator':'0','denominator':'1'}),
        ):
            bad=deepcopy(d['diagnostic']);mutate(bad)
            with self.assertRaises(ValueError):m.inspect_candidate(bad['candidate'],d['inputs']['inputs'],r['inputs'])
        for mutate in (
            lambda x:x['diagnostic'].__setitem__('immutable_control_reference',dict(m.CONTROL,json_pointer='/tracks/candidate')),
            lambda x:x['started'].__setitem__('planned_candidate_core_call_count',True),
            lambda x:x['input_readback'].__setitem__('inputs_reference',{}),
            lambda x:x['inputs']['inputs']['incumbent']['schedule'][0]['targets'][next(iter(x['inputs']['inputs']['incumbent']['schedule'][0]['targets']))].__setitem__('target_weight',.1),
        ):
            bad=deepcopy(d);mutate(bad)
            with self.assertRaises(ValueError):m.validate_links(tid,bad,r)

    def test_hard_pins_and_no_production_imports(self):
        for p,h in [(m.PRODUCER,m.PRODUCER_SHA),(m.INPUT_READER,m.INPUT_READER_SHA)]+[(Path(r['path']),r['sha256']) for r in (m.CONTROL,m.CONTROL_PUB,m.CONTROL_AUDIT)]:
            self.assertEqual(m.sha(p.read_bytes()),h)
        with patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.guard({str(m.PRODUCER):'a'*64})
            read.assert_not_called()
        import ast
        tree=ast.parse(m.SOURCE.read_text())
        modules=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]+[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        self.assertFalse(any(n.startswith(('backtest','scripts')) for n in modules))

if __name__=='__main__':unittest.main()
