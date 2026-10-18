"""Independent bounded math plus saved-snapshot projection; no fresh bank build."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path('E:/Git/us_ratchet')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
bank=load('c_independent_bank',ROOT/'backtest/ndx_full_pool_training_matrix_binding_research.py')
moments=load('c_independent_moments',ROOT/'backtest/ndx_full_pool_training_moments_research.py')
oracle=load('c_independent_fraction_oracle',ROOT/'tmp/training_matrix_c_independent_preparation_20261009_v1/fraction_oracle.py')
DETAILS={}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def matrix(cells=None):
    return dict(model_id=moments.MODEL,ordered_security_ids=['SYNTHETIC_A','SYNTHETIC_B'],training_dates=['2026-01-01','2026-01-02','2026-01-03'],shape=[3,2],cells=deepcopy(cells or [list(r) for r in oracle.ROWS]))
def faithful(value):
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,list):return [faithful(x) for x in value]
    if isinstance(value,dict):return {k:faithful(v) for k,v in value.items()}
    return value
def numeric_pointers(value,pointer=''):
    if type(value) in (int,Decimal):yield pointer,value
    elif isinstance(value,list):
        for i,v in enumerate(value):yield from numeric_pointers(v,pointer+'/'+str(i))
    elif isinstance(value,dict):
        for k,v in value.items():yield from numeric_pointers(v,pointer+'/'+k.replace('~','~0').replace('/','~1'))

class IndependentTrainingReview(unittest.TestCase):
    def test_01_pre_io_and_independent_actual_math(self):
        options=[dict(include_covariance=True),dict(include_covariance=True,work_budget=True),dict(work_budget=-1),dict(work_budget='1'),dict(work_budget=1.0),dict(work_budget=1),dict(covariance_model='UNKNOWN'),dict(include_saved_dual_benchmarks=1)]
        with patch.object(Path,'read_bytes',side_effect=AssertionError('PREPARAMETER FILE READ')),patch.object(bank,'_load_fixed',side_effect=AssertionError('SOURCEADAPTER FORBIDDEN')):
            for value in options:
                with self.subTest(value=value),self.assertRaises(ValueError):bank.read_source_bound_training_bank(**value)
            for state in ({},False,{'requested':0}):
                with self.assertRaises(NotImplementedError):bank.read_source_bound_training_bank(resume_state=state)
            with self.assertRaises(NotImplementedError):bank.read_source_bound_training_bank(include_covariance=True,work_budget=0,covariance_model=bank.LEGACY_MODEL)
        expected=oracle.independently_reconstruct();data=matrix();before=deepcopy(data);boundaries={}
        for budget,(means,pairs,spent) in oracle.PREFIX_EXPECTATIONS.items():
            with patch.object(Path,'read_bytes',side_effect=AssertionError('PURE MOMENT IO')):
                out=moments.prepare_exact_training_moments(matrix=data,work_budget=budget)
            self.assertEqual((out['work']['mean_columns_completed'],out['work']['pair_entries_completed'],out['work']['spent']),(means,pairs,spent))
            self.assertEqual(out['work']['unused'],budget-spent)
            if budget<56:self.assertIsNone(out['full_covariance'])
            else:self.assertEqual(out['full_covariance'],[[str(x) for x in r] for r in expected['sigma']])
            boundaries[str(budget)]=dict(means=means,pairs=pairs,spent=spent)
        actual=dict(add=0,sub=0,mul=0,div=0);results=[];zero_shrink=[]
        methods={'add':'__add__','sub':'__sub__','mul':'__mul__','div':'__truediv__'}
        originals={k:getattr(Fraction,v) for k,v in methods.items()}
        def wrap(name):
            def operation(a,b):
                actual[name]+=1
                if name=='mul' and a==Fraction(7,20) and b==0:zero_shrink.append((str(a),str(b)))
                result=originals[name](a,b)
                results.append(result);return result
            return operation
        with patch.object(Fraction,'__add__',wrap('add')),patch.object(Fraction,'__sub__',wrap('sub')),patch.object(Fraction,'__mul__',wrap('mul')),patch.object(Fraction,'__truediv__',wrap('div')):
            out=moments.prepare_exact_training_moments(matrix=data,work_budget=56)
        self.assertEqual(actual,dict(add=18,sub=18,mul=15,div=5));self.assertEqual(len(zero_shrink),1)
        observed=[max(abs(v.numerator).bit_length() for v in results),max(v.denominator.bit_length() for v in results)]
        self.assertEqual(out['work']['intermediate_max_fraction_bits'],observed)
        self.assertEqual([t['sample'] for t in out['pair_tasks']],['1','1','4'])
        self.assertEqual(data,before)
        self.assertTrue(all(v is False for v in out['permissions'].values()))
        self.assertFalse(out['certificate']['independently_checked'])
        null=matrix();null['cells'][1][1]=None
        with patch.object(Fraction,'__add__',side_effect=AssertionError('NULL NUMERICAL WORK')):
            blocked=moments.prepare_exact_training_moments(matrix=null,work_budget=999)
        self.assertEqual(blocked['work']['source_blocked_tasks'],5);self.assertEqual(blocked['work']['spent'],0)
        DETAILS['math']=dict(actual_fraction_operators=actual,intermediate_bits_observed=observed,offdiag_explicit_second_shrink_zero_calls=1,atomic_boundaries=boundaries,expected_covariance=[['1','13/20'],['13/20','4']],independent_oracle=True)

    def test_02_shared_prefix_eval_separation_and_tamper(self):
        first=dict(matrix=matrix(),window_ordinals=[0,1]);second=dict(matrix=matrix([['0','0'],['1','1'],['2','2']]),window_ordinals=[2])
        items=[deepcopy(first),deepcopy(second)]
        remaining,spent,counts=bank._estimate_unique(items,79,moments)
        self.assertEqual((remaining,spent),(15,64))
        self.assertEqual([i['moments']['work']['spent'] for i in items],[56,8])
        self.assertEqual(sum(counts.values()),64);self.assertEqual(items[0]['window_ordinals'],[0,1])
        self.assertIsNone(items[1]['moments']['full_covariance'])
        columns=[dict(original_channel=dict(return_rows=[dict(split_only_return_exact=str(i+c)) for i in range(5)])) for c in range(2)]
        before=bank._matrix(columns,0,3,['2026-01-01','2026-01-02','2026-01-03'],['A','B'])
        columns[0]['original_channel']['return_rows'][3]['split_only_return_exact']='999'
        self.assertEqual(before,bank._matrix(columns,0,3,before['training_dates'],['A','B']))
        partial=moments.prepare_exact_training_moments(matrix=matrix(),work_budget=24)
        for mutate in [lambda r:r['mean_tasks'].pop(),lambda r:r['pair_tasks'].pop(),lambda r:r['work'].update(spent=0),lambda r:r['certificate'].update(independently_checked=True)]:
            changed=deepcopy(partial);mutate(changed)
            with self.assertRaises(ValueError):moments.check_exact_training_moment_certificate(matrix=matrix(),result=changed)
        for resume in ({},False,{'digest':'rehashed'}):
            with self.assertRaises(NotImplementedError):moments.prepare_exact_training_moments(matrix=None,work_budget=56,resume_state=resume)
        DETAILS['shared_prefix']=dict(total_budget=79,spent=64,unused=15,per_matrix_spent=[56,8],shared_window_ordinals=[0,1],scope='Pure synthetic estimator prefix; dedup grouping independently checked against full saved snapshot in test04',evaluation_changes_excluded_from_training_matrix=True,same_helper_certificate_tamper_rejection='Four actual saved-result shape/accounting attacks, not independent algorithm proof')

    def test_03_bounded_host_guard_readview_not_real_bank(self):
        with tempfile.TemporaryDirectory(prefix='matrix_c_guard_') as directory:
            path=Path(directory)/'source';path.write_bytes(b'fixed fixture source');expected=digest(path.read_bytes())
            forwarded=[]
            def source_guard():
                self.assertEqual(digest(path.read_bytes()),expected);forwarded.append(True)
            reader=SimpleNamespace(read_conditional_full_pool_sources=lambda **kwargs:dict(facts={'consumed_source_hashes':{str(path):expected}},final_guard=source_guard))
            # Explicit orchestration fixture only: no source reader execution or
            # private real-bank reconstruction is hidden in this test.
            with patch.object(bank,'_load_fixed',side_effect=[reader,SimpleNamespace()]),patch.object(bank,'_build_bank',return_value={'work':{}}):
                saved=bank.read_source_bound_training_bank()
            self.assertEqual(len(forwarded),1)
            saved['facts']['implementation_references'].clear();saved['facts']['work'].clear()
            self.assertEqual(saved['final_guard']()['calls'],2)
            regular=bank._read_regular;drifted=[]
            for reference in (bank._READER,bank._MOMENTS,*bank._CONTRACTS,(Path(bank.__file__),bank._LOADED_CODE_SHA)):
                target=reference[0]
                def read_view(p):return b'changed only read view' if p==target else regular(p)
                with patch.object(bank,'_read_regular',side_effect=read_view):
                    with self.assertRaisesRegex(ValueError,'Fixed source bytes changed'):saved['final_guard']()
                drifted.append(str(target))
            raw_read=Path.read_bytes
            with patch.object(Path,'read_bytes',lambda p:b'drift view' if p==path else raw_read(p)):
                with self.assertRaises(AssertionError):saved['final_guard']()
            self.assertEqual(path.read_bytes(),b'fixed fixture source')
            DETAILS['guard']=dict(scope='Fresh bounded host orchestration with explicit fake fixed reader/fake build, real final_guard code and existing fixed code/contract refs; not original real-bank post-return drift',fixed_refs_simulated_drift_rejected=drifted,source_fixture_readview_rejected=True,returned_facts_mutation_did_not_change_guard=True,source_adapter_calls=0,real_bank_builds=0,disk_source_mutation=False)

    def test_04_whole_saved_snapshot_mapping_against_original_channels(self):
        snapshot=ROOT/'tmp/full_pool_training_author_20261009_v1/facts.json'
        raw=snapshot.read_bytes();self.assertEqual(digest(raw),'8c08f93d2d15bcca49dbbfaac03360f9897e1a72a4d1be34f1b04f9edc0ec955')
        data=json.loads(raw);del raw
        self.assertEqual(len(data['source_columns']),77);self.assertEqual(len(data['windows']),78)
        self.assertEqual(len(data['unique_training_matrices']),32)
        self.assertEqual([data['coverage'][k] for k in ['securities','issuers','original_provenance']],[77,76,101])
        self.assertTrue(all(v is False for v in data['permissions'].values()))
        self.assertEqual(len(data['source_facts']['source_checks']),10)
        self.assertTrue(all(v['status']=='SOURCE_BLOCKED' for v in data['source_facts']['source_checks']))
        for k in ['qualified_inventory','qualified_denominator','current_account','current_new_money']:self.assertIsNone(data[k])
        self.assertEqual(data['plan_rows'],[]);self.assertEqual(data['work']['spent'],0)
        originals=[];refs=[];tokens=0
        for c in data['source_columns']:
            ref=c['source_reference'];raw=Path(ref['path']).read_bytes();self.assertEqual(digest(raw),ref['sha256'])
            original=json.loads(raw,parse_float=Decimal);faith=faithful(original)
            self.assertEqual(c['original_channel'],faith)
            self.assertEqual(c['raw_reference'],faith['raw_reference']);self.assertEqual(c['receipt_reference'],faith['receipt_reference'])
            pointers=dict(numeric_pointers(original));self.assertEqual(set(pointers),set(c['original_numeric_tokens']))
            for pointer,number in pointers.items():
                token=c['original_numeric_tokens'][pointer]
                lexeme=raw[token['utf8_byte_start']:token['utf8_byte_stop']].decode('utf-8')
                self.assertEqual(lexeme,token['original_lexeme']);self.assertEqual(Decimal(lexeme),number);tokens+=1
            originals.append(faith);refs.append(ref)
        columns=data['source_columns'];ids=[c['coordinate']['security_id'] for c in columns]
        self.assertEqual(len(set(ids)),77)
        reconstructed=[];matrix_groups={};train_missing_counts={};eval_missing_counts={};cells=0;endpoint_associations=0
        for ordinal,window in enumerate(data['windows']):
            decision_index,wi=divmod(ordinal,13)
            base=originals[0]['decisions'][decision_index];source_window=base['windows'][wi]
            a,b,e,f=[source_window[k] for k in ['training_return_index_start','training_return_index_stop','evaluation_return_index_start','evaluation_return_index_stop']]
            self.assertEqual((window['window_ordinal'],window['cutoff'],window['window_index']),(ordinal,base['cutoff'],wi))
            self.assertEqual((window['training_start'],window['training_stop'],window['evaluation_start'],window['evaluation_stop']),(a,b,e,f))
            self.assertEqual((b-a,f-e,e),(126,126,b))
            dates=originals[0]['calendar'][a+1:b+1]
            expected_matrix=dict(model_id=moments.MODEL,ordered_security_ids=ids,training_dates=dates,shape=[126,77],cells=[])
            train_missing=[];eval_missing=[]
            for ci,original in enumerate(originals):
                sw=original['decisions'][decision_index]['windows'][wi]
                self.assertEqual([sw[k] for k in ['training_return_index_start','training_return_index_stop','evaluation_return_index_start','evaluation_return_index_stop']],[a,b,e,f])
                self.assertEqual(window['original_window_status_by_column'][ci],sw['status'])
                for role,start,stop,destination,counts in [('train',a,b,train_missing,train_missing_counts),('eval',e,f,eval_missing,eval_missing_counts)]:
                    missing=[g for g in range(start,stop) if original['return_rows'][g]['split_only_return_exact'] is None]
                    if missing:
                        destination.append(dict(column=ci,security_id=ids[ci],global_return_indices=missing))
                        ticker=columns[ci]['coordinate']['ticker'];counts[ticker]=counts.get(ticker,0)+1
            self.assertEqual(window['training_blocked_sid_rows'],train_missing)
            self.assertEqual(window['evaluation_diagnostic']['blocked_sid_rows'],eval_missing)
            self.assertFalse(window['evaluation_diagnostic']['numeric_values_used_in_training'])
            self.assertEqual(window['training_dates'],dates)
            for r in range(126):
                row=[];g=a+r
                for ci,original in enumerate(originals):
                    ret=original['return_rows'][g]
                    self.assertEqual(ret['session'],dates[r]);self.assertEqual(ret['previous_session'],original['calendar'][g])
                    # These equality checks bind every compact return and both
                    # endpoint object roles, not merely a representative sample.
                    self.assertEqual(columns[ci]['original_channel']['return_rows'][g],ret)
                    self.assertEqual(columns[ci]['original_channel']['quote_rows'][g],original['quote_rows'][g])
                    self.assertEqual(columns[ci]['original_channel']['quote_rows'][g+1],original['quote_rows'][g+1])
                    row.append(ret['split_only_return_exact']);cells+=1;endpoint_associations+=2
                expected_matrix['cells'].append(row)
            encoded=json.dumps(expected_matrix,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode();fingerprint=digest(encoded)
            group=window['unique_matrix_index'];actual=data['unique_training_matrices'][group]
            self.assertEqual(actual['matrix'],expected_matrix);self.assertEqual(actual['matrix_sha256'],fingerprint)
            self.assertEqual(window['training_numeric_payload_sha256'],fingerprint)
            self.assertIsNone(actual['moments'])
            self.assertEqual(actual['numerical_status'],'SOURCE_BLOCKED' if train_missing else 'NUMERIC_READY_NOT_SOURCE_QUALIFIED')
            payload_key=encoded;prior=matrix_groups.get(payload_key)
            if prior is None:matrix_groups[payload_key]=group
            else:self.assertEqual(group,prior)
            reconstructed.append(group)
        for group,item in enumerate(data['unique_training_matrices']):
            self.assertEqual(item['window_ordinals'],[i for i,g in enumerate(reconstructed) if g==group])
        self.assertEqual(len(matrix_groups),32);self.assertEqual(cells,756756)
        self.assertEqual(train_missing_counts,{'WDC':51,'LRCX':27});self.assertEqual(eval_missing_counts,{'WDC':15,'LRCX':1})
        self.assertEqual(sum(x['numerical_status']!='SOURCE_BLOCKED' for x in data['unique_training_matrices']),12)
        # Pure accessor implementation checked on two nonlocal global indices
        # per column; the full data mapping above covers all coordinates.
        accessor=0
        with patch.object(Path,'read_bytes',side_effect=AssertionError('ACCESSOR IO FORBIDDEN')):
            for ci in range(77):
                for ordinal,r in [(0,73),(77,93)]:
                    out=bank.get_training_cell(data,window_ordinal=ordinal,row=r,column=ci);g=data['windows'][ordinal]['training_start']+r
                    self.assertEqual(out['original_return'],originals[ci]['return_rows'][g]);self.assertEqual(out['return_pointer'],f'/return_rows/{g}')
                    self.assertEqual([q['pointer'] for q in out['price_endpoints']],[f'/quote_rows/{g}',f'/quote_rows/{g+1}'])
                    self.assertEqual(out['source_reference'],refs[ci]);self.assertFalse(out['source_authentication'])
                    out['source_reference'].clear();self.assertEqual(columns[ci]['source_reference'],refs[ci]);accessor+=1
        DETAILS['snapshot']=dict(snapshot_sha256='8c08f93d2d15bcca49dbbfaac03360f9897e1a72a4d1be34f1b04f9edc0ec955',original_channels=77,numeric_pointer_set_and_tokens=tokens,coordinates=cells,whole_quote_endpoint_associations=endpoint_associations,unique_payloads=32,ready_unique_payloads=12,training_missing=train_missing_counts,evaluation_missing=eval_missing_counts,nonlocal_accessor_checks=accessor,source_adapter_calls=0,real_bank_builds=0,raw_replays=0,true77_moments=0,scope='Complete saved-snapshot projection versus original channel JSON; not fresh raw/provider/PIT authentication')

if __name__=='__main__':unittest.main()
