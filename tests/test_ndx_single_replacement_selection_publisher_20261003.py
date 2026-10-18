import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_single_replacement_selection_20261003 as m
from scripts import ndx_single_replacement_execution_independent_readback_20261003 as audit
from scripts import ndx_single_replacement_shard_worker_20261003 as worker
from test_ndx_single_replacement_execution_independent_readback_20261003 import physical as prior_physical


@contextmanager
def physical(root):
    with prior_physical(root) as c:
        first=audit.ref(audit.REQUEST_PATH,audit.REQUEST_SHA)
        with patch.object(worker,'OUTPUT',audit.PARENT),patch.object(worker,'load_common',return_value=c),patch.object(worker,'resource'):
            request=worker.run(execute=True,max_shards=1,prior_result_reference=first)
        with patch.object(audit,'REQUEST_PATH',Path(request['path'])),patch.object(audit,'REQUEST_SHA',request['sha256']):ar=audit.readback(execute=True)
        refs={('preparation_'+k if k!='preparation' else k):r for k,r in c['refs'].items()}
        refs.update(request=request,execution_audit=ar,execution_reader=m.ref(audit.SOURCE,audit.LOADED))
        registration=dict(schema='SINGLE_REPLACEMENT_SELECTION_SOURCE_REGISTRATION_V1',status='REGISTERED_SAVED_COMPLETE_DOMAIN_SELECTION_ONLY',integer_count=560,scenario_count=40,input_references=refs,**m.FLAGS)
        p=root/'selection_registration.json';p.write_bytes(m.enc(registration));rr=m.ref(p,m.sha(p.read_bytes()))
        with patch.multiple(m,BOUND={k:(r['path'],r['sha256']) for k,r in c['refs'].items()},EXECUTION=audit.PARENT,AUDIT_ROOT=audit.OUTPUT,PREP=audit.PREP,PREP_AUDIT=audit.AUDIT,OUTPUT=root/'selection',TOTAL=560),patch.object(m,'resource'):
            yield rr


class Tests(unittest.TestCase):
    def test_physical_full_journal_selection_without_evaluation(self):
        with tempfile.TemporaryDirectory() as t,physical(Path(t)) as rr:
            with patch.object(worker,'run',side_effect=AssertionError('No producer')):
                refs=m.run(registration_reference=rr,execute=True)
            d=json.loads(Path(refs['selection']['path']).read_bytes())['selection']['document']
            self.assertEqual(d['integer_count'],560);self.assertEqual(len(d['rows']),40)
            self.assertEqual(sum(r['feasible_count']+r['infeasible_count'] for r in d['rows']),560)
            with self.assertRaises(ValueError):m.run(registration_reference=rr,execute=True)

    def test_pending_and_final_drift_preserve_raw_no_retry(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')):
            with self.assertRaises(ValueError):m.run(execute=True)
        for mode in ('source','output','extra'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t,physical(Path(t)) as rr:
                save=m.save
                def changed(name,value,**kw):
                    r=save(name,value,**kw)
                    if name=='publication.json':
                        p=m.EXECUTION/'shard-0000'/'journal.jsonl' if mode=='source' else m.OUTPUT/('started.json' if mode=='output' else 'extra')
                        with p.open('ab') as f:f.write(b' ')
                    return r
                with patch.object(m,'save',changed),self.assertRaises(ValueError):m.run(registration_reference=rr,execute=True)
                self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'raw_selection.json').exists())

    def test_locator_and_trailing_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as t,physical(Path(t)) as rr:
            c=m.load_inputs(rr);c['audit']['shards'][0]['inspection']['records'][1]['byte_start']+=1
            with self.assertRaises(ValueError):list(m.stream_records(c))
            c=m.load_inputs(rr);p=m.EXECUTION/'shard-0001'/'journal.jsonl'
            with p.open('ab') as f:f.write(b'\n')
            with self.assertRaises(ValueError):list(m.stream_records(c))


if __name__=='__main__':unittest.main()
