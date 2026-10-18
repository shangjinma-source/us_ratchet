from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_nav_reference_metrics_20261003 as w
from backtest import ndx_multidecision_account_inputs_research as prepare
from test_ndx_multidecision_account_inputs_research import fixture as account_fixture
from test_ndx_same_window_nav_reference_metrics_research import fixture as nav_fixture, resign


def physical(root,missing=False):
    def put(path,obj,raw=False):
      path.parent.mkdir(parents=True,exist_ok=True);b=obj if raw else w.enc(obj);path.write_bytes(b);return w.ref(path,w.sha(b))
    a=account_fixture();source=a['price_evidence']['document'];days=source['calendar253']
    removed={'2026-04-03','2026-05-25','2026-06-19','2026-07-03','2026-09-07'};days=[x for x in days if x not in removed];d=date.fromisoformat(days[0])
    while len(days)<253:
      d-=timedelta(days=1)
      if d.weekday()<5:days.insert(0,d.isoformat())
    source['calendar253']=days
    for i,r in enumerate(source['rows']):
      ch=r['channel'];ch['quote_rows']=[dict(session=x,nominal_open_exact='100',nominal_close_exact='101') for x in days];ch['quote_rows_sha256']=prepare.digest(ch['quote_rows']);a['price_evidence']['readback']['per_channel'][i]['quote_rows_sha256']=ch['quote_rows_sha256']
    inputs=prepare.prepare_multidecision_account_inputs(**a);calendar=inputs['rows'][0]['tracks'][0]['stateful_input']['calendar'];assert len(calendar)==120
    alignment=nav_fixture()['alignment'];template=deepcopy(alignment['rows'][0]);alignment['session_dates']=days;alignment['rows']=[]
    for i,d in enumerate(days):
      row=deepcopy(template);row['session']=d
      for mode in w.MODES:row['conversions'][mode].update(nav_usd_exact='2' if d==calendar[0] else '1',nav_usd_decimal='saved original display')
      alignment['rows'].append(row)
    if missing:alignment['rows'][-5]['conversions'][w.MODES[0]].update(status='MISSING_ALIGNMENT_INPUT',reason='NO_SAME_SESSION_FX',nav_usd_exact=None,nav_usd_decimal=None)
    resign(alignment);aflags=dict.fromkeys(('point_in_time_verified','benchmark_qualified','execution_authorized'),False)
    ar=put(root/'alignment/alignment.json',dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_DOCUMENT_V1',alignment=alignment,source_hashes={},nav_manifest_preserved={'original':'manifest'},nav_snapshot_preserved={'original':'snapshot'},fx_capture_manifest_preserved={'original':'fx'},**aflags));put(root/'alignment/started.json',{})
    ap=put(root/'alignment/publication.json',dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_CONVERSION_ONLY',alignment_reference=ar,source_hashes={},**aflags));reader=put(root/'alignment_reader.py',b'# never execute',True)
    aa=put(root/'alignment_audit.json',dict(schema='NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_V1',status='PASS',alignment_sha256=ar['sha256'],publication_sha256=ap['sha256'],reader_sha256=reader['sha256'],point_in_time_verified=False,benchmark_qualified=False,account_executed=False))
    flags=dict.fromkeys(('account_simulation_performed','point_in_time_verified','execution_authorized','formal_benchmark_passed','promotion_allowed'),False)
    ir=put(root/'account/inputs.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1',inputs=inputs,source_hashes={},**flags));put(root/'account/started.json',{})
    ip=put(root/'account/publication.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1',status='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS',inputs_reference=ir,source_hashes={},**flags));ireader=put(root/'account_reader.py',b'# never execute',True)
    ia=put(root/'account_audit.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',scope='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION',inputs_reference=ir,publication_reference=ip,reader_sha256=ireader['sha256'],inspection=dict(lane_count=8,track_count=16,coordinate_count=48),**dict.fromkeys(('producer_called','account_engine_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed'),False)))
    refs=dict(alignment=ar,alignment_publication=ap,alignment_audit=aa,alignment_reader=reader,account_inputs=ir,account_publication=ip,account_audit=ia,account_reader=ireader)
    for n in w.CODE:put(root/'backtest'/f'{n}.py',(w.ROOT/'backtest'/f'{n}.py').read_bytes(),True)
    return {k:(v['path'],v['sha256']) for k,v in refs.items()}

class Tests(unittest.TestCase):
 def test_pending_no_io_and_fixed_three_code_bytes(self):
    for n,h in w.CODE.items():self.assertEqual(w.sha((w.ROOT/'backtest'/f'{n}.py').read_bytes()),h)
    pending=dict(w.BOUND);pending['account_inputs']=(pending['account_inputs'][0],None)
    with patch.object(w,'BOUND',pending),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
      with self.assertRaisesRegex(ValueError,'pending'):w.load_inputs()
 def test_complete_physical_load_private_nav_only_120_119_and_missing_mode(self):
    for missing in (False,True):
      with self.subTest(missing=missing),tempfile.TemporaryDirectory() as td:
        root=Path(td);bound=physical(root,missing)
        with patch.object(w,'ROOT',root),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',root/'out'),patch.object(w,'resource'):
          c=w.load_inputs();self.assertEqual(len(c['args']['reference_calendar']['dates']),120)
          def forbidden(**kwargs):raise AssertionError('account metrics must not be called')
          private=w.private_core
          def isolated(sources):
            module=private(sources);module.account_twr_metrics=forbidden;return module
          with patch.object(w,'private_core',side_effect=isolated):rr=w.run(execute=True)
          with self.assertRaisesRegex(ValueError,'Create only'):w.run(execute=True)
        doc=w.decode(Path(rr['path']).read_bytes());modes=doc['metrics']['modes'];self.assertEqual(len(modes),2)
        self.assertEqual(modes[w.MODES[1]]['metrics']['interval_count'],119);self.assertEqual(modes[w.MODES[1]]['metrics']['maximum_drawdown'],{'numerator':'1','denominator':'2'})
        self.assertEqual(len(modes[w.MODES[0]]['observations']),120)
        if missing:self.assertIsNone(modes[w.MODES[0]]['metrics'])
        self.assertFalse(doc['account_metrics_calculated']);self.assertFalse(doc['subscription_redemption_modeled'])
 def test_wrong_calendar_or_audit_link_refused_before_metrics(self):
    with tempfile.TemporaryDirectory() as td:
      root=Path(td);bound=physical(root)
      with patch.object(w,'ROOT',root),patch.object(w,'BOUND',bound):c=w.load_inputs()
      bad=deepcopy(c['docs']);bad['account_audit']['inputs_reference']['sha256']='f'*64
      with self.assertRaises(ValueError):w.project_inputs(bad,c['refs'])
      bad=deepcopy(c['docs']);p=bad['account_inputs']['inputs'];p['rows'][3]['tracks'][1]['stateful_input']['calendar'].pop(5);p['content_sha256']=w.sha(w.enc({k:v for k,v in p.items() if k!='content_sha256'}))
      with self.assertRaises(ValueError):w.project_inputs(bad,c['refs'])
 def test_none_raw_first_and_postpublication_source_drift(self):
    for invalid in (True,False):
      with self.subTest(invalid=invalid),tempfile.TemporaryDirectory() as td:
        root=Path(td);bound=physical(root);private=w.private_core;save=w.save
        def core(s):
          m=private(s)
          if invalid:m.reference_metrics=lambda **kwargs:None
          return m
        def saved(name,obj,emergency=False):
          r=save(name,obj,emergency)
          if not invalid and name=='publication.json':Path(bound['alignment'][0]).write_bytes(b'drift')
          return r
        with patch.object(w,'ROOT',root),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',root/'out'),patch.object(w,'resource'),patch.object(w,'private_core',side_effect=core),patch.object(w,'save',side_effect=saved):
          with self.assertRaises(ValueError):w.run(execute=True)
        self.assertTrue((root/'out/raw_result.json').exists());self.assertTrue((root/'out/failure.json').exists())

if __name__=='__main__':unittest.main()
