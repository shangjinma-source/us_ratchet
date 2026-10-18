from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_scoring_history_20261003 as m
from backtest import ndx_multidecision_scoring_history_research as core
from test_ndx_bulk_long_window_channels_20261003 import fixture as parent_fixture
from test_ndx_multidecision_scoring_history_research import fixture as channel_fixture


def fixture():
    docs,refs,raw=parent_fixture();a=channel_fixture()
    docs['history']['requirements']['reference_calendar']=dict(ticker='AAPL',dates=a['reference_calendar'],source_reference=dict(path='calendar',sha256='c'*64))
    return docs,refs,raw


class Tests(unittest.TestCase):
    def test_inventory_and_sidecars_preserved_and_bad_metadata_rejected(self):
        docs,refs,_=fixture();r=m.prepare(docs,refs)
        self.assertEqual(len(r),77);self.assertEqual(len({x['coordinate']['issuer_id'] for x in r}),76)
        self.assertEqual(r[0]['reference_calendar'],docs['history']['requirements']['reference_calendar']['dates'])
        for change in [lambda d:d['panel']['panel']['observed_provenance_and_missing'].pop(),lambda d:d['history']['projection_evidence']['complete_panel_sidecars'].pop(m.SIDECARS[-1]),lambda d:d['history']['requirements']['ticker_observations_preserved']['AAPL']['complete_bridge_row'].update(ticker='FOREIGN')]:
            b=deepcopy(docs);change(b)
            with self.assertRaises((ValueError,KeyError)):m.prepare(b,refs)

    def test_real_core_partial_floor_and_result_binding(self):
        a=channel_fixture();a['bridge_row']['event_policy_bridge']['regular_floor']='2025-02-24';r=core.materialize_scoring_history_channel(**a)
        request=dict(coordinate=dict(ticker=r['ticker']),**{k:a[k] for k in ('raw_reference','receipt_reference','bridge_row','reference_calendar')})
        m.validate_channel(r,request,a['tzif_bytes'],a['outer_inventory_contract'])
        self.assertTrue(any(d['status']=='BLOCKED_FULL13_SCORING_SUPPLY' for d in r['decisions']))
        for key in ('promotion_allowed','score_computed','missing_or_blocked_slots_dropped'):
            b=deepcopy(r);b[key]=True
            with self.assertRaises(ValueError):m.validate_channel(b,request,a['tzif_bytes'],a['outer_inventory_contract'])

    def test_physical_parents_private_core_and_drift(self):
        docs,refs,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bound={}
            for role in m.BOUND:
                path=root/(role+'.json');blob=m.encoded(docs[role]) if role in docs else b'synthetic report'
                path.write_bytes(blob);bound[role]=(path.name,m.sha(blob));refs[role]=dict(path=str(path),sha256=m.sha(blob))
            # Rebind only metadata references that the pure adapter actually consumes.
            docs['history_publication']['requirements_reference']=refs['history']
            for t,item in docs['history']['requirements']['ticker_observations_preserved'].items():
                i=next(i for i,r in enumerate(docs['bridge']['rows']) if r['ticker']==t)
                item['bridge_reference']=dict(refs['bridge'],json_pointer=f'/rows/{i}')
            tz=root/'NY';tz.write_bytes(b'TZ');docs['bridge']['source_hashes']={str(tz):m.sha(b'TZ')}
            for role in ('bridge','history'):
                blob=m.encoded(docs[role]);(root/bound[role][0]).write_bytes(blob);bound[role]=(bound[role][0],m.sha(blob));refs[role]['sha256']=m.sha(blob)
            # bridge hash changed: all preserved bridge references must follow it.
            for item in docs['history']['requirements']['ticker_observations_preserved'].values():item['bridge_reference']['sha256']=refs['bridge']['sha256']
            blob=m.encoded(docs['history']);(root/'history.json').write_bytes(blob);bound['history']=('history.json',m.sha(blob));refs['history']['sha256']=m.sha(blob)
            docs['history_publication']['requirements_reference']=refs['history']
            blob=m.encoded(docs['history_publication']);(root/'history_publication.json').write_bytes(blob);bound['history_publication']=('history_publication.json',m.sha(blob))
            docs['history_audit'].update(requirements_sha256=bound['history'][1],publication_sha256=bound['history_publication'][1],reader_sha256=bound['history_audit_reader'][1])
            blob=m.encoded(docs['history_audit']);(root/'history_audit.json').write_bytes(blob);bound['history_audit']=('history_audit.json',m.sha(blob))
            with patch.object(m,'ROOT',root),patch.object(m,'BOUND',bound),patch.object(m,'NY_SOURCE',tz),patch.object(m,'NY_SHA',m.sha(b'TZ')):
                loaded=m.load_inputs();self.assertEqual(len(loaded[3]),77);self.assertEqual(loaded[-1].__file__,str(m.CORE))
                tz.write_bytes(b'drift')
                with self.assertRaises(ValueError):m.guard(loaded[2],loaded[1])

    def test_pending_before_io_and_started_failure_no_retry(self):
        with patch.object(m,'CORE_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.load_inputs()
            read.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'out'),patch.object(m,'load_inputs',return_value=({}, {}, {}, [], b'TZ',None)),patch.object(m,'space'):
            with self.assertRaises(KeyError):m.run(execute=True)
            self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'started.json').exists())
            with self.assertRaises(ValueError):m.run(execute=True)

if __name__=='__main__':unittest.main()
