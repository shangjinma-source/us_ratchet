"""Pure V5 declarations and repeat gaps; all wrappers/references are synthetic."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_prospective_history_parent_view_research_v5 as module
from backtest import ndx_prospective_gap_history_research_v5 as gap
from backtest import ndx_accounted_source_prefix_research_v1 as prefix
from scripts import ndx_prospective_observation_writer_v3_20261009 as oldwriter
from test_ndx_prospective_gap_history_research_v5 import arguments,reference


def wrap(history,tag='first'):
    h=deepcopy(history);inputs=dict(parent=h['parent_references'],capture=h['capture_references']);sources={}
    module.legacy.declarations(h,sources);module.legacy.declarations(inputs,sources)
    document=dict(schema=module.WRAPPER_SCHEMA,history=h,input_references=inputs,source_hashes=sources,**module.FLAGS)
    refs={role:reference('synthetic/'+tag+'/'+role)for role in module.ROLES}
    publication=dict(schema=module.PUBLICATION_SCHEMA,status=module.PUBLICATION_STATUS,history_reference=refs['reference'],
        input_references=inputs,source_hashes=deepcopy(sources),**module.FLAGS)
    audit_sources=deepcopy(sources)
    for role in ('reference','publication_reference','reader_reference'):module.ref(refs[role],audit_sources)
    audit=dict(schema=module.READBACK_SCHEMA,status=module.READBACK_STATUS,history_reference=refs['reference'],publication_reference=refs['publication_reference'],
        reader_sha256=refs['reader_reference']['sha256'],input_references=inputs,source_hashes=audit_sources,counts=module.gap_counts(h),
        entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,current_live_cache_read_or_reverified=False,**module.FLAGS)
    return dict(refs,document=document,publication=publication,readback=audit)


def fixture():
    args=arguments(dates=('2026-10-09','2026-10-12','2026-10-13'))
    args['capture_references']={role:reference('synthetic/fresh-gap-capture/'+role)for role in module.ROLES}
    return args,gap.extend_gap_history(**args)


def next_arguments(parent,previous_args,new_days,expired,start,tag):
    view=module.inspect_parent_history_v5(parent);days=[r['session']for r in view['known_typed_rows']]
    raw={t:previous_args['source_bytes'][t]+b''.join((day+',10,12,8,10,100\n').encode()for day in new_days)for t in ('QQQ','SPY')}
    accounted={};sources={t:reference('synthetic/'+tag+'/full/'+t,raw[t])for t in ('QQQ','SPY')};prefixes={};evidences={}
    for t in ('QQQ','SPY'):
        accounted[t],_=prefix.derive_accounted_prefix(source_bytes=previous_args['source_bytes'][t],source_reference=previous_args['source_references'][t],accounted_sessions=days,scope_start=days[0])
        derived,evidence=prefix.derive_accounted_prefix(source_bytes=raw[t],source_reference=sources[t],accounted_sessions=days+list(expired),scope_start=days[0])
        prefixes[t]=reference('synthetic/'+tag+'/prefix/'+t,derived)
        evidences[t]=reference('synthetic/'+tag+'/evidence/'+t,gap.prefix_evidence_bytes(evidence))
    return dict(parent=parent,capture_references={role:reference('synthetic/'+tag+'/capture/'+role)for role in module.ROLES},
        source_bytes=raw,source_references=sources,accounted_baseline_bytes=accounted,actual_baseline_bytes=deepcopy(previous_args['actual_baseline_bytes']),
        prefix_references=prefixes,prefix_evidence_references=evidences,capture_started_at=start,capture_completed_at=start,
        tzif_bytes=previous_args['tzif_bytes'],tzif_reference=previous_args['tzif_reference'])


class ParentViewV5Tests(unittest.TestCase):
    def test_real_v3_and_synthetic_v4_delegate_with_honest_legacy_provenance(self):
        refs=oldwriter.PARENT_BOUND;real=deepcopy(refs)
        for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:real[key]=json.loads(Path(refs[role]['path']).read_bytes())
        synthetic=arguments()['parent']
        for parent in (real,synthetic):
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure view IO')):view=module.inspect_parent_history_v5(parent)
            self.assertEqual(view['schema'],module.VIEW_SCHEMA);self.assertTrue(view['legacy_checker_called'])
            self.assertEqual(view['legacy_checker_reference']['sha256'],module.LEGACY_VIEW_SHA256)
            self.assertEqual(view['pending_source_sessions'],[]);self.assertEqual(view['accounted_prefix_evidence'],{})
            self.assertEqual(view['accounted_prefix_role'],module.LEGACY_PREFIX_ROLE)

    def test_v5_mixed_complete_partition_roles_month_and_no_fake_v4(self):
        args,h=fixture();parent=wrap(h);before=deepcopy(parent)
        with patch.object(module.legacy,'inspect_parent_history_v4',side_effect=AssertionError('Fake legacy wrapper')):
            view=module.inspect_parent_history_v5(parent)
        self.assertEqual(parent,before);self.assertEqual((view['typed_row_count'],view['observation_count'],view['gap_count']),(71,2,9))
        self.assertFalse(view['legacy_checker_called']);self.assertEqual(view['last_observed_session'],'2026-10-08')
        self.assertEqual(view['last_accounted_session'],'2026-10-09')
        self.assertEqual([v['session']for v in view['pending_source_sessions']],['2026-10-12'])
        self.assertEqual([v['session']for v in view['excluded_not_completed_source_sessions']],['2026-10-13'])
        self.assertEqual(view['accounted_baseline_references'],h['accounted_prefix_references'])
        self.assertNotEqual(view['accounted_baseline_references'],view['full_capture_source_references'])
        self.assertEqual(view['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
        self.assertTrue(all(view[key]is False for key in module.FLAGS))
        self.assertNotIn('prior_state_preserved',module.parent_state_for_gap(view))

    def test_repeat_v5_gap_then_no_expired_preserves_latest_pending(self):
        args,h=fixture();first=wrap(h)
        second_args=next_arguments(first,args,('2026-10-14',),('2026-10-12',),'2026-10-13T20:02:00+00:00','second')
        second=gap.extend_gap_history(**second_args);second_parent=wrap(second,'second');view=module.inspect_parent_history_v5(second_parent)
        self.assertEqual((view['typed_row_count'],view['observation_count'],view['gap_count']),(72,2,10))
        self.assertEqual(second['known_typed_rows_preserved'],h['known_typed_rows']);self.assertEqual(second['observations'],h['observations'])
        third_args=next_arguments(second_parent,second_args,(),(),'2026-10-13T20:03:00+00:00','third')
        third=gap.extend_gap_history(**third_args);last=module.inspect_parent_history_v5(wrap(third,'third'))
        self.assertEqual(third['status'],'NO_EXPIRED_SESSION_TO_APPEND');self.assertEqual(last['known_typed_rows'],view['known_typed_rows'])
        self.assertEqual([v['session']for v in last['pending_source_sessions']],['2026-10-13'])
        self.assertEqual([v['session']for v in last['excluded_not_completed_source_sessions']],['2026-10-14'])

    def test_coordinated_resigned_result_cannot_delete_previous_pending_date(self):
        _,first_h=fixture();first=wrap(first_h);prior=module.inspect_parent_history_v5(first)
        args=arguments(dates=('2026-10-09','2026-10-13','2026-10-14'),start='2026-10-13T20:02:00+00:00',end='2026-10-13T20:02:01+00:00')
        args['capture_references']={role:reference('synthetic/forged-capture/'+role)for role in module.ROLES}
        for t in ('QQQ','SPY'):
            args['source_references'][t]=reference('synthetic/forged-full/'+t,args['source_bytes'][t])
            raw,evidence=prefix.derive_accounted_prefix(source_bytes=args['source_bytes'][t],source_reference=args['source_references'][t],
                accounted_sessions=[r['session']for r in prior['known_typed_rows']],scope_start=prior['known_typed_rows'][0]['session'])
            args['prefix_references'][t]=reference('synthetic/forged-prefix/'+t,raw)
            args['prefix_evidence_references'][t]=reference('synthetic/forged-evidence/'+t,gap.prefix_evidence_bytes(evidence))
        h=gap.extend_gap_history(**args)
        h.update(parent_references=deepcopy(prior['parent_references']),parent_state_reference=deepcopy(prior['parent_references']['reference']),
            prior_state_preserved=module.parent_state_for_gap(prior),known_typed_rows=deepcopy(prior['known_typed_rows']),
            known_typed_rows_preserved=deepcopy(prior['known_typed_rows']),parent_typed_row_count=prior['typed_row_count'],
            new_missed_observation_count=0,gap_classifications=[],status='NO_EXPIRED_SESSION_TO_APPEND')
        for t in ('QQQ','SPY'):
            h['source_evidence'][t]['new_session_dates']=['2026-10-13','2026-10-14']
            h['source_evidence'][t]['accounted_baseline_reference']=prior['accounted_baseline_references'][t]
        for index,item in enumerate(h['pending_source_sessions']+h['excluded_not_completed_source_sessions']):
            item['source_session_pointer_by_ticker']={t:'/plan/source_evidence/'+t+'/new_session_dates/'+str(index)for t in ('QQQ','SPY')}
        h['source_hashes'].update(prior['source_hashes']);h['source_reference_claims']=deepcopy(h['source_hashes'])
        with self.assertRaisesRegex(ValueError,'Previously captured source sessions cannot disappear'):
            module.inspect_parent_history_v5(wrap(h,'coordinated-forgery'))

    def test_partition_missing_duplicate_reordered_and_wrong_timing_reject(self):
        _,history=fixture()
        for mode in ('missing','duplicate','reordered','timing','month','consumed'):
            h=deepcopy(history)
            if mode=='missing':h['pending_source_sessions']=[]
            elif mode=='duplicate':h['excluded_not_completed_source_sessions']=deepcopy(h['pending_source_sessions'])
            elif mode=='reordered':h['gap_classifications'],h['pending_source_sessions']=h['pending_source_sessions'],h['gap_classifications']
            elif mode=='timing':h['pending_source_sessions'][0]['conservative_next_weekday_open_utc']='2026-10-12T13:30:00+00:00'
            elif mode=='month':h['first_actual_observed_session_by_month']['2026-10']='2026-10-09'
            else:h['pending_source_sessions'][0]['consumes_month_first_opportunity']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):module.inspect_parent_history_v5(wrap(h))

    def test_prefix_summary_counts_indexes_raw_lists_and_false_zero_reject(self):
        _,history=fixture()
        for key,value in [('prefix_byte_count',True),('byte_stop',1),('excluded_before_scope_rows_count',False),
            ('suffix_original_row_indexes',[]),('accounted_original_row_indexes',[]),('excluded_before_scope_rows',[]),
            ('excluded_before_scope_rows_sha256','A'*64),('source_authenticity_verified',0)]:
            h=deepcopy(history);h['accounted_prefix_evidence']['QQQ'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):module.inspect_parent_history_v5(wrap(h))

    def test_prior_snapshot_recursion_prefix_rewrite_and_known_authority_reject(self):
        _,history=fixture()
        for mode in ('recursive','known','attempt','baseline','wrapper_authority','count_bool'):
            h=deepcopy(history)
            if mode=='recursive':h['prior_state_preserved']['prior_state_preserved']={}
            elif mode=='known':h['known_typed_rows_preserved'][0]['seal_status']='UNKNOWN'
            elif mode=='attempt':h['parent_attempt_inventory']=[]
            elif mode=='baseline':h['baseline_role']=module.PREFIX_ROLE
            elif mode=='count_bool':h['parent_actual_observation_count']=True
            parent=wrap(h)
            if mode=='wrapper_authority':parent['publication']['production_generator_authorized']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):module.inspect_parent_history_v5(parent)

    def test_summary_hash_is_canonical_list_without_artifact_lf(self):
        args,_=fixture();days=[r['session']for r in module.inspect_parent_history_v5(args['parent'])['known_typed_rows']]
        _,evidence=prefix.derive_accounted_prefix(source_bytes=args['source_bytes']['QQQ'],source_reference=args['source_references']['QQQ'],
            accounted_sessions=days+['2026-10-09'],scope_start=days[0])
        summary=module.prefix_evidence_summary(evidence);self.assertEqual(summary,gap.prefix_evidence_summary(evidence))
        for key in ('excluded_before_scope_rows','excluded_before_scope_ohlc_diagnostics'):
            self.assertNotIn(key,summary);self.assertEqual(summary[key+'_sha256'],hashlib.sha256(module.legacy.compact.encoded(evidence[key])).hexdigest())


if __name__=='__main__':unittest.main()
