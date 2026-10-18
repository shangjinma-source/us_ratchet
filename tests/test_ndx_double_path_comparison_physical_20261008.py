from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import json,tempfile,unittest
import test_ndx_double_signed_paths_physical_20261008 as signed_fixture
from scripts import ndx_double_replacement_signed_paths_20261008 as signed
from scripts import ndx_double_replacement_signed_paths_independent_readback_20261008 as signed_reader
from scripts import ndx_double_replacement_path_comparison_20261008 as m
from scripts import ndx_double_replacement_path_comparison_independent_readback_20261008 as reader
from backtest import ndx_cash_flow_return_accounting_research as buyonly
from backtest import ndx_cash_fork_reference_window_research as metrics

@contextmanager
def physical(root,*,blocked=False):
    original=signed_fixture.fixture
    def full_old():
        a=original()
        for row in a['old_paired_rows']:
            zero=deepcopy(row['paths']['candidate']['accounting_inputs'])
            for session in zero['sessions']:
                session['buy_shares']={}
                for key in ('open_prices','close_prices'):session[key]={sid:v for sid,v in session[key].items()if sid in zero['initial']['holdings']}
            row['paths']['same_flow_zero_trade_control']=dict(accounting_inputs=zero,account=buyonly.account_path(**zero))
        if blocked:
            r=a['selection']['rows'][0];r.update(status='NO_FEASIBLE',selected=None,feasible_count=0,infeasible_count=r['integer_count'])
            del a['old_paired_rows'][1]['paths']['candidate']['accounting_inputs']['sessions'][0]['open_prices']['C']
        return a
    root.mkdir(parents=True,exist_ok=True)
    # The physical parent helper requires every selected record while writing
    # original gzip. Absent-source coverage is tested separately at pure level.
    (root/'signed_sources').mkdir()
    with patch.object(signed_fixture,'fixture',full_old):signed_registration,constants=signed_fixture.physical(root/'signed_sources')
    reg=json.loads(Path(signed_registration['path']).read_bytes());pp=reg['input_references']['paired_publication'];pub=json.loads(Path(pp['path']).read_bytes());pub.update(orders_executed=False,point_in_time_verified=False,promotion_allowed=False);Path(pp['path']).write_bytes(m.enc(pub));pp['sha256']=m.filehash(pp['path']);constants['BOUND']['paired_publication']=(pp['path'],pp['sha256']);Path(signed_registration['path']).write_bytes(m.enc(reg));signed_registration['sha256']=m.filehash(signed_registration['path'])
    with patch.multiple(signed,**constants),patch.object(signed,'resource'),patch.multiple(signed_reader,OUTPUT=root/'signed_audit',PUBLISHER_SHA=signed.LOADED):
        paths=signed.run(registration_reference=signed_registration,execute=True)
        audit=signed_reader.readback(registration_reference=signed_registration,result_reference=paths['result'],publication_reference=paths['publication'],execute=True)
        reg=json.loads(Path(signed_registration['path']).read_bytes());paired=reg['input_references']['paired'];old=json.loads(Path(paired['path']).read_bytes())['rows']
        refs={k:m.ref(p,m.filehash(p))for k,(p,h)in m.BOUND.items()};refs.update(signed_registration=signed_registration,signed_result=paths['result'],signed_publication=paths['publication'],signed_audit=audit,paired=paired,paired_publication=reg['input_references']['paired_publication'])
        def put(role,name,value=None,raw=None):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw if raw is not None else m.enc(value));refs[role]=m.ref(p,m.filehash(p));return refs[role]
        groups={};incpaths=[];mappings=[]
        for row in old:
            e=row['input_row']['cash_event'];key=e['decision_date']+'|'+e['amount_usd']
            if key not in groups:
                groups[key]=len(incpaths);zero=row['paths']['same_flow_zero_trade_control'];a=deepcopy(zero['account']);a.update(schema='SIGNED_FLOW_FROZEN_INCUMBENT_OPEN_ACCOUNT_V1',initial=deepcopy(zero['accounting_inputs']['initial']),daily=a.pop('rows'),cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES',flow_policy='FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN',risk_is_order_gate=False);incpaths.append(dict(path_id=key,account=a))
            mappings.append(dict(scenario_id=row['scenario_id'],path_id=key,original_input_row=row['input_row'],input_reference=row['input_reference']))
        inc=put('incumbent','incumbent/accounts.json',dict(paths=incpaths,scenario_mappings=mappings,source_hashes={}))
        same=[];nav=[]
        for i,row in enumerate(old):
            zero=row['paths']['same_flow_zero_trade_control'];calendar=[zero['accounting_inputs']['initial']['session']]+[d['session']for d in zero['account']['rows']];mapping=mappings[i];pi=groups[mapping['path_id']];account=incpaths[pi]['account'];baseline=metrics.metrics(calendar,[Fraction(1)]*len(calendar))
            same.append(dict(scenario_id=row['scenario_id'],input_row=row['input_row'],original_input_reference=row['input_reference'],calendar=calendar,candidate_paired_row_reference=m.pointer(paired,f'/rows/{i}'),incumbent_mapping_reference=m.pointer(inc,f'/scenario_mappings/{i}'),incumbent_path_reference=m.pointer(inc,f'/paths/{pi}'),incumbent_mapping_preserved=mapping,observations=dict(same_flow_incumbent=[dict(reference=m.pointer(inc,f'/paths/{pi}/account/daily/{j}'),source_row=d)for j,d in enumerate(account['daily'])]),metrics=dict(same_flow_incumbent=baseline)))
            nav.append(dict(scenario_id=row['scenario_id'],input_row=row['input_row'],paired_row_reference=m.pointer(paired,f'/rows/{i}'),comparison=dict(calendar=calendar,roles={k:deepcopy(baseline)for k in ('same_flow_zero_trade_control','fund_012922_cny_nav_reference')}),observations=dict(same_flow_zero_trade_control=[dict(reference=m.pointer(paired,f'/rows/{i}/paths/same_flow_zero_trade_control/account/rows/{j}'),source_row=d)for j,d in enumerate(zero['account']['rows'])],fund_nav=[dict(encoding='SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE',value_field='nav',source_row=dict(session=d,nav_date=d,nav=1.0),reference=dict(path='synthetic-original-NAV',sha256='a'*64,json_pointer=f'/nav/rows/{j}'))for j,d in enumerate(calendar)])))
        for role,rows in (('sameflow',same),('reference',nav)):put(role,role+'/comparison.json',dict(rows=rows,source_hashes={}))
        for role,schema,status,key in [('sameflow','TOPUP_SAME_FLOW_COMPARISON_PUBLICATION_V1','PUBLISHED_CONDITIONAL_DIAGNOSTIC_COMPARISON','comparison_reference'),('reference','TOPUP_REFERENCE_COMPARISON_PUBLICATION_V1','PUBLISHED_FOUR_ROLE_DIAGNOSTICS_NOT_FORMAL_ADMISSION','comparison_reference'),('incumbent','INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V1','PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS','account_reference')]:
            put(role+'_publication',role+'/publication.json',dict(schema=schema,status=status,**{key:refs[role]},source_hashes={},orders_executed=False,point_in_time_verified=False,promotion_allowed=False));put(role+'_audit',role+'_audit.md',raw=b'# Explicit synthetic saved reference report')
        registration=put('registration','comparison-registration.json',dict(schema='DOUBLE_REPLACEMENT_COMPARISON_SOURCE_REGISTRATION_V1',status='REGISTERED_SAVED_SIGNED_PATH_COMPARISON_ONLY',scenario_count=40,input_references=deepcopy(refs),**m.FLAGS));refs.pop('registration')
        original_adapter=m.load_adapter
        def configured_adapter(r):
            adapter=original_adapter(r)
            for key in ('BOUND','SELECTION_PATHS','SELECTION_READER_SHA','TOTAL','OUTPUT','CODE'):setattr(adapter,key,deepcopy(getattr(signed,key)))
            adapter.resource=lambda **kw:None
            return adapter
        with patch.object(m,'BOUND',{k:(refs[k]['path'],refs[k]['sha256'])for k in m.BOUND}),patch.object(m,'FUTURE_PATHS',{k:refs[k]['path']for k in m.FUTURE_PATHS}),patch.object(m,'OUTPUT',root/'comparison'),patch.object(m,'load_adapter',configured_adapter):yield registration

class Tests(unittest.TestCase):
    def test_full_twenty_role_physical_double_compare_and_independent(self):
        with tempfile.TemporaryDirectory()as t,physical(Path(t))as registration:
            out=m.run(registration_reference=registration,execute=True);doc=json.loads(Path(out['comparison']['path']).read_bytes());self.assertEqual(doc['comparison']['candidate_status_counts']['AVAILABLE_NEW_SIGNED'],40)
            self.assertIn('DOUBLE_REPLACEMENT',doc['comparison']['policy_asymmetry'])
            original=reader.private
            def private(reference,sources):
                instance=original(reference,sources)
                if reference['path']==str(reader.PRODUCER):instance.BOUND=m.BOUND;instance.FUTURE_PATHS=m.FUTURE_PATHS;instance.OUTPUT=m.OUTPUT;instance.load_adapter=m.load_adapter
                return instance
            with patch.multiple(reader,PRODUCER_SHA=m.LOADED,INSPECTOR_SHA=m.filehash(reader.INSPECTOR),PARENT=m.OUTPUT,OUTPUT=Path(t)/'independent'),patch.object(reader,'private',side_effect=private),patch.object(metrics,'metrics',side_effect=AssertionError('No reference/producer metric in readback')):
                r=reader.readback(registration_reference=registration,comparison_reference=out['comparison'],publication_reference=out['publication'],execute=True);report=json.loads(Path(r['path']).read_bytes());self.assertEqual(report['status'],'PASS');self.assertEqual(len(report['input_references']),20)
    def test_interrupted_comparison_preserves_raw_no_retry(self):
        with tempfile.TemporaryDirectory()as t,physical(Path(t))as registration:
            c=m.load_inputs(registration);function=c['pure'].compare_selected_double_replacement_paths
            def failed(**kwargs):raise KeyboardInterrupt('Synthetic comparison interruption')
            with patch.object(m,'load_inputs',return_value=c),patch.object(c['pure'],'compare_selected_double_replacement_paths',side_effect=failed):
                with self.assertRaises(ValueError):m.run(registration_reference=registration,execute=True)
            self.assertTrue((m.OUTPUT/'raw_comparison.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())

if __name__=='__main__':unittest.main()
