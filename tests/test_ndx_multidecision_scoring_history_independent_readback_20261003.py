from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_scoring_history_independent_readback_20261003 as m
from test_ndx_multidecision_scoring_history_20261003 import fixture as parents
from test_ndx_multidecision_scoring_history_inspection_research import saved_case
from backtest import ndx_multidecision_scoring_history_inspection_research as oracle


def physical(root):
    docs,_,raws=parents();refs={};bound={};base={};parent=root/'parent';parent.mkdir()
    def write(path,value):
        blob=value if type(value) is bytes else m.encoded(value);path.write_bytes(blob);return m.ref(path,m.sha(blob))
    for role in m.BOUND:refs[role]=m.ref(root/(role+'.json'),'a'*64)
    refs['history_audit_reader']=write(root/'history_audit_reader.json',b'prior reader')
    refs['history_audit_report']=write(root/'history_audit_report.json',b'prior report')
    for ticker,o in docs['history']['requirements']['ticker_observations_preserved'].items():
        r=write(root/(ticker+'.raw'),raws[ticker]['raw_bytes']);rr=write(root/(ticker+'.receipt'),raws[ticker]['receipt_bytes']);br=next(x for x in docs['bridge']['rows'] if x['ticker']==ticker)
        br['new_raw_reference']=r;br['new_receipt_reference']=rr;o['raw_reference']=r;o['receipt_reference']=rr;o['complete_bridge_row']=deepcopy(br)
    tz=root/'NY';tz.write_bytes(b'TZ');docs['bridge']['source_hashes']={str(tz):m.sha(b'TZ')}
    refs['bridge']=write(root/'bridge.json',docs['bridge'])
    for o in docs['history']['requirements']['ticker_observations_preserved'].values():o['bridge_reference'].update(refs['bridge'])
    refs['panel']=write(root/'panel.json',docs['panel']);refs['history']=write(root/'history.json',docs['history'])
    docs['history_publication']['requirements_reference']=refs['history'];refs['history_publication']=write(root/'history_publication.json',docs['history_publication'])
    docs['history_audit'].update(requirements_sha256=refs['history']['sha256'],publication_sha256=refs['history_publication']['sha256'],reader_sha256=refs['history_audit_reader']['sha256']);refs['history_audit']=write(root/'history_audit.json',docs['history_audit'])
    for role,r in refs.items():bound[role]=(Path(r['path']).name,r['sha256']);base[r['path']]=r['sha256']
    producer=root/'producer.py';producer.write_bytes(b'never executed')
    for p,h in [(producer,m.sha(producer.read_bytes())),(m.CORE,m.CORE_SHA),(tz,m.sha(b'TZ'))]:base[str(p)]=h
    sources=deepcopy(base);hr=docs['history']['requirements'];rows=[]
    for i,coordinate in enumerate(hr['universe']):
        o=hr['ticker_observations_preserved'][coordinate['ticker']]
        for k in ('raw_reference','receipt_reference'):sources[o[k]['path']]=o[k]['sha256']
        ds=[dict(cutoff=c,status='BLOCKED_FULL13_SCORING_SUPPLY',complete_thirteen_window_numeric_supply=False,windows=[dict(status='BLOCKED_WINDOW')]*13) for c in m.CUTOFFS]
        ch=dict(status='PARTIAL_NUMERIC_SUPPLY_FULL_SCORING_BLOCKED',regular_floor=None,decisions=ds)
        cr=write(parent/f'channel_{i:03d}.json',ch)
        rows.append(dict(index=i,coordinate=coordinate,channel_reference=cr,status=ch['status'],regular_floor=None,history_observation_reference=dict(refs['history'],json_pointer='/requirements/ticker_observations_preserved/'+coordinate['ticker']),original_identity_assumed_window=o['identity_assumed_window'],decision_coverage=[dict(cutoff=d['cutoff'],status=d['status'],complete_thirteen_window_numeric_supply=False,blocked_window_count=13) for d in ds]))
    outer=dict(inventory_reference=dict(refs['panel'],json_pointer='/panel/universe'),security_count=77,issuer_count=76,observed_provenance_count=101,preserved_sidecar_references={n:dict(refs['panel'],json_pointer='/'+n) for n in m.SIDECARS})
    index=dict(schema='MULTIDECISION_SCORING_HISTORY_AGGREGATE_V1',status='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_INDEPENDENT_READBACK',input_references=refs,source_hashes=sources,rows=rows,window_contract=m.CONTRACT,reference_calendar=hr['reference_calendar'],outer_inventory_contract=outer,original_provenance_and_missing=hr['observed_provenance_and_missing'],preserved_evidence_sidecars={n:docs['panel'][n] for n in m.SIDECARS},security_count=77,issuer_count=76,observed_security_count=101,preserved_sidecar_count=7,raw_decode_count=77,score_computed=False,unequal_window_pooling_allowed=False,full_ndx_universe_certified=False,new_independent_numeric_readback_completed=False,historical_retrospective_only=True,**dict.fromkeys(m.FLAGS,False))
    ir=write(parent/'index.json',index);pub=dict(schema='MULTIDECISION_SCORING_HISTORY_PUBLICATION_V1',status=index['status'],input_references=refs,source_hashes=sources,index_reference=ir,**dict.fromkeys(m.FLAGS,False));pr=write(parent/'publication.json',pub)
    write(parent/'started.json',dict(schema='MULTIDECISION_SCORING_HISTORY_STARTED_V1',input_references=refs,source_hashes=base,planned_channel_count=77,retry_allowed=False,started_at_utc='2026-10-03T00:00:00+00:00',**dict.fromkeys(m.FLAGS,False)))
    return dict(ROOT=root,PARENT=parent,OUTPUT=root/'readback',BOUND=bound,PRODUCER=producer,PRODUCER_SHA=m.sha(producer.read_bytes()),INDEX_SHA=ir['sha256'],PUBLICATION_SHA=pr['sha256'],NY_SOURCE=tz,NY_SHA=m.sha(b'TZ')),index,pub,docs,refs


class Tests(unittest.TestCase):
    def test_physical_closure_no_producer_import_and_omission_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            pins,index,pub,docs,refs=physical(Path(tmp))
            with patch.multiple(m,**pins):
                loaded=m.load_inputs();self.assertEqual(len(loaded[2]),77);self.assertEqual(loaded[4].__file__,str(m.INSPECTOR))
                for change in (lambda x:x['rows'].reverse(),lambda x:x.update(security_count=True),lambda x:x['preserved_evidence_sidecars'].pop(m.SIDECARS[0]),lambda x:x['rows'][0].update(index=False)):
                    b=deepcopy(index);change(b)
                    with self.assertRaises((ValueError,KeyError)):m.inspect_inventory(b,pub,docs,refs)
                (pins['PARENT']/'failure.json').write_text('{}')
                with self.assertRaises(ValueError):m.guard(loaded[1],refs)

    def test_independent_arithmetic_same_bytes_and_blocked_summary(self):
        a,ch=saved_case();result=oracle.inspect_scoring_history_channel(saved_channel=ch,**a);self.assertEqual(result['window_count'],78)
        row=dict(status=ch['status'],regular_floor=ch['regular_floor'],decision_coverage=[dict(cutoff=d['cutoff'],status=d['status'],complete_thirteen_window_numeric_supply=d['complete_thirteen_window_numeric_supply'],blocked_window_count=0) for d in ch['decisions']])
        m.inspect_index_row(row,ch);row['decision_coverage'][0]['blocked_window_count']=False
        with self.assertRaises(ValueError):m.inspect_index_row(row,ch)

    def test_pending_no_io_and_postwrite_drift_no_retry(self):
        with patch.object(m,'INDEX_SHA',None),patch.object(Path,'read_bytes') as read,patch.object(Path,'exists') as exists:
            with self.assertRaises(ValueError):m.readback(execute=True)
            read.assert_not_called();exists.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            pins,_,_,_,_=physical(Path(tmp))
            with patch.multiple(m,**pins):
                original=m.save
                def save(path,value,**kw):
                    r=original(path,value,**kw)
                    if path.name=='independent_readback.json':(pins['PARENT']/'channel_000.json').write_bytes(b'drift')
                    return r
                # Source orchestration test only: numerical oracle independently tested above.
                with patch.object(m.types,'ModuleType',wraps=m.types.ModuleType),patch.object(m,'save',side_effect=save),patch('shutil.disk_usage',return_value=type('Disk',(),{'free':10**12})()):
                    real_load=m.load_inputs
                    def load():
                        out=list(real_load());out[4]=type('Oracle',(),{'inspect_scoring_history_channel':staticmethod(lambda **kw:dict(status='PASS',window_count=78))})();return tuple(out)
                    with patch.object(m,'load_inputs',side_effect=load):
                        with self.assertRaises(ValueError):m.readback(execute=True)
                self.assertTrue((pins['OUTPUT']/'failure.json').exists())
                with self.assertRaises(ValueError):m.readback(execute=True)

if __name__=='__main__':unittest.main()
