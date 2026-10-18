from copy import deepcopy
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import ndx_cash_neighbor_selected_paths_20261003 as m
from backtest import ndx_cash_neighbor_selected_path_requests_research as pure
from backtest import ndx_cash_flow_return_accounting_research as account
from backtest import ndx_research_json_rows_stream as streaming
from test_ndx_cash_neighbor_selected_path_requests_research import fixture


def staged(root):
    inputs=fixture();prepared=pure.prepare_selected_path_requests(**inputs);entries=[]
    for row in prepared['rows']:
        folder=root/f'scenario-{row["scenario_index"]:02d}';folder.mkdir();r=m.save(folder/'request.json',dict(request=row,source_hashes={}))
        entries.append(dict(scenario_index=row['scenario_index'],scenario_id=row['scenario_id'],status=row['status'],request_reference=r))
    return entries


class Tests(unittest.TestCase):
    def test_pending_before_io(self):
        with tempfile.TemporaryDirectory()as td,patch.object(m,'OUTPUT',Path(td)/'new'),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):m.run(execute=True)

    def test_full_new_paths_and_immutable_controls(self):
        with tempfile.TemporaryDirectory()as td,patch.object(m,'OUTPUT',Path(td)),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=m.MIN_FREE_BYTES)):
            entries=staged(Path(td));before=[Path(x['request_reference']['path']).read_bytes()for x in entries]
            out=m.execute_requests(entries,{},dict(account_core=account,request_core=pure))
            self.assertEqual(len(out['completed_rows']),40);self.assertEqual(len(out['attempted_scenario_ids']),40);self.assertEqual(out['undispatched_scenario_ids'],[])
            self.assertEqual(before,[Path(x['request_reference']['path']).read_bytes()for x in entries]);self.assertFalse(out['controls_executed'])
            raw=json.loads((Path(td)/'scenario-00/raw.json').read_bytes());self.assertEqual(raw['account']['rows'][0]['holdings_after'],{'A':12,'Z':0})

    def test_resource_before_dispatch_and_raw_exception_retained(self):
        with tempfile.TemporaryDirectory()as td,patch.object(m,'OUTPUT',Path(td)),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=m.MIN_FREE_BYTES-1)):
            entries=staged(Path(td));core=SimpleNamespace(account_path=lambda **kw:(_ for _ in ()).throw(AssertionError('must not dispatch')))
            out=m.execute_requests(entries,{},dict(account_core=core,request_core=pure));self.assertEqual(len(out['undispatched_scenario_ids']),40);self.assertEqual(out['unresolved_scenario_ids'],[])
        with tempfile.TemporaryDirectory()as td,patch.object(m,'OUTPUT',Path(td)),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=m.MIN_FREE_BYTES)):
            entries=staged(Path(td));core=SimpleNamespace(account_path=lambda **kw:(_ for _ in ()).throw(RuntimeError('failure')))
            out=m.execute_requests(entries,{},dict(account_core=core,request_core=pure));self.assertEqual(len(out['undispatched_scenario_ids']),39);self.assertEqual(out['unresolved_scenario_ids'],['scenario-0']);self.assertTrue((Path(td)/'scenario-00/raw.json').exists());self.assertTrue((Path(td)/'scenario-00/postcheck.json').exists())
            again=m.execute_requests(entries,{},dict(account_core=core,request_core=pure));self.assertEqual(again['attempted_scenario_ids'],[])

    def test_paired_stream_full_eof_authentication_precedes_all_dispatch(self):
        for bad in (False,True):
            with tempfile.TemporaryDirectory()as td:
                root=Path(td);out=root/'out';out.mkdir();sel=root/'selection';sel.mkdir();cases=fixture()['cases'];entries=[];preps=[];sources={}
                for i,c in enumerate(cases):
                    folder=sel/f'scenario-{i:02d}';folder.mkdir();lr=m.save(folder/'ledger.jsonl',{});start=m.save(folder/'started.json',{})
                    sr=m.save(folder/'selection.json',dict(schema='CASH_NEIGHBOR_SOURCE_BOUND_CASE_SELECTION_V1',scenario_index=i,selection=c['selection'],ledger_reference=lr,requires_final_publication=True));pr=m.save(folder/'publication.json',dict(selection_reference=sr,ledger_reference=lr,requires_final_publication=True))
                    cr=m.save(root/f'contract-{i}.json',c['prepared']);sources[cr['path']]=cr['sha256'];entries.append(dict(scenario_index=i,scenario_id=c['selection']['scenario_id'],status=c['selection']['status'],selection_reference=sr,publication_reference=pr,ledger_reference=lr));preps.append(dict(contract_reference=cr))
                raw=m.enc(dict(schema='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1',rows=[c['old_paired_row']for c in cases],source_hashes={}))
                # Fixture original refs use 'paired'; pure must see the same real declaration.
                paired=root/'paired';paired.write_bytes(raw+(b' trailing'if bad else b''));r=dict(paired=m.ref(paired,m.sha(raw)),selection_audit=m.ref('audit','a'*64));d=dict(selection=dict(cases=entries,source_hashes=sources),preparation=dict(rows=preps),paired_publication=dict(source_hashes={}))
                def prepare(c,i):
                    c['old_paired_reference']['path']='paired'
                    c['old_paired_reference']['sha256']='a'*64
                    return pure.prepare_case(c,i)
                core=SimpleNamespace(prepare_case=prepare,LANES=pure.LANES,CLOCKS=pure.CLOCKS)
                with patch.object(m,'OUTPUT',out),patch.object(m,'SEL',sel):
                    if bad:
                        with self.assertRaises(ValueError):m.prepare_requests(d,r,{},dict(stream_core=streaming,request_core=core))
                    else:self.assertEqual(len(m.prepare_requests(d,r,{},dict(stream_core=streaming,request_core=core))[0]),40)
                self.assertFalse(list(out.glob('*/raw.json')));self.assertFalse(list(out.glob('*/started.json')))

    def test_post_drift_durable_raw_and_no_double_execution(self):
        with tempfile.TemporaryDirectory()as td,patch.object(m,'OUTPUT',Path(td)),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=m.MIN_FREE_BYTES)):
            entries=staged(Path(td));calls=[]
            def changed(**kw):
                self.assertTrue((Path(td)/'scenario-00/started.json').exists());calls.append(1);r=account.account_path(**kw)
                (Path(td)/'scenario-00/request.json').write_text('{}');return r
            out=m.execute_requests(entries,{},dict(account_core=SimpleNamespace(account_path=changed),request_core=pure));self.assertEqual(calls,[1]);self.assertEqual(out['unresolved_scenario_ids'],['scenario-0']);self.assertIsNotNone(json.loads((Path(td)/'scenario-00/raw.json').read_bytes())['account']);self.assertEqual(json.loads((Path(td)/'scenario-00/postcheck.json').read_bytes())['outcome'],'VALIDATION_FAILURE')

if __name__=='__main__':unittest.main()
