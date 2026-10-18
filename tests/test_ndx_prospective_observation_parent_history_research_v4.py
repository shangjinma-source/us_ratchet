"""Synthetic V3 migration and repeat V4 actual append, no output or IO entrypoint."""
import base64
from copy import deepcopy
from hashlib import sha256
import unittest
from unittest.mock import patch
from pathlib import Path

from backtest import ndx_prospective_observation_parent_history_research_v4 as module
from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
from test_ndx_prospective_gap_history_research_v3 import reference
from test_ndx_prospective_observation_gap_parent_payload_20261009_v3 import arguments


def observation_for(parent,core,args):
    payload=core.prepare_observation_payload(**args)
    refs={role:reference('observation/'+args['session']+'/'+role)for role in module.OBSERVATION_ROLES}
    capture={role:reference('capture/'+args['session']+'/'+role)for role in module.ROLES}
    capture['reference']=args['capture']['reference']
    inputs=dict(parent={role:deepcopy(parent[role])for role in module.ROLES},capture=capture)
    sources=deepcopy(payload['source_hash_claims'])
    module.declarations(parent,sources);module.declarations(inputs,sources)
    payload.update(input_references=inputs,source_hashes=deepcopy(sources),**writer.FLAGS)
    receipt=dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',
        payload_reference=refs['payload_reference'],observation_id=payload['observation_id'],
        month_first_actual_observation=payload['month_first_actual_observation'],timing_classification=payload['timing_classification'],
        input_references=deepcopy(inputs),source_hashes=deepcopy(sources),**writer.FLAGS)
    audited=deepcopy(sources)
    for item in refs.values():module.ref(item,audited)
    known=args['known_typed_rows']
    audit=dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3',status='PASS',
        payload_reference=refs['payload_reference'],receipt_reference=refs['receipt_reference'],reader_sha256=refs['reader_reference']['sha256'],
        parent_history_reference=parent['reference'],input_references=deepcopy(inputs),source_hashes=audited,
        writer_called=False,payload_core_called=False,old_audit_repeated=False,
        counts=dict(parent_typed_row_count=len(known),parent_actual_observation_count=sum(r['kind']=='PROSPECTIVE_OBSERVED_SESSION'for r in known),
            parent_observed_count=sum(r['kind']!='MISSED_OBSERVATION'for r in known),parent_gap_count=sum(r['kind']=='MISSED_OBSERVATION'for r in known),
            new_observation_count=1,month_first_actual_observation=receipt['month_first_actual_observation'],timing_classification=receipt['timing_classification']),
        **writer.FLAGS)
    return dict(payload=payload,receipt=receipt,audit=audit,**refs)


def fixture():
    core,data,args=arguments();parent=data['parent']
    # Upstream synthetic fixture predates the parent identity source association.
    for entry in parent['document']['history']['observations']:
        r=entry['observation_identity']['parent_reference']
        for claims in entry['original_source_hash_claims'].values():module.ref(r,claims)
        for key in ('document','publication','readback'):module.ref(r,parent[key]['source_hashes'])
        for key in ('source_hashes','source_reference_claims'):module.ref(r,parent['document']['history'][key])
    return dict(parent=parent,observation=observation_for(parent,core,args))


def wrap(history):
    refs={role:reference('history/'+str(history['typed_row_count'])+'/'+role)for role in module.ROLES}
    inputs=dict(parent=history['parent_references'],observation=history['observation_references'])
    sources=deepcopy(history['source_hashes']);module.declarations(inputs,sources)
    flags=dict.fromkeys(module.WRAPPER_FALSE,False)
    d=dict(schema=module.WRAPPER_SCHEMA,history=history,input_references=inputs,source_hashes=deepcopy(sources),**flags)
    p=dict(schema=module.PUBLICATION_SCHEMA,status=module.PUBLICATION_STATUS,history_reference=refs['reference'],
        input_references=deepcopy(inputs),source_hashes=deepcopy(sources),**flags)
    audited=deepcopy(sources)
    for item in refs.values():module.ref(item,audited)
    a=dict(schema=module.READBACK_SCHEMA,status=module.READBACK_STATUS,history_reference=refs['reference'],
        publication_reference=refs['publication_reference'],reader_sha256=refs['reader_reference']['sha256'],
        input_references=deepcopy(inputs),source_hashes=audited,counts=module.history_counts_v4(history),
        entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,
        current_live_cache_read_or_reverified=False,**flags)
    return dict(document=d,publication=p,readback=a,**refs)


def next_fixture(history,prior_observation):
    parent=wrap(history);core,_,args=arguments();view=module.inspect_parent_history_v4(parent)
    args.update(parent_reference=parent['reference'],parent_readback_reference=parent['readback_reference'],
        known_typed_rows=view['known_typed_rows'],parent_attempt_inventory=view['parent_attempt_inventory'],session='2026-10-09',
        writer_started_at_utc='2026-10-09T20:01:00+00:00',writer_completed_at_utc='2026-10-09T20:01:01+00:00')
    capture=dict(reference=reference('capture-oct9'),started_at_utc='2026-10-09T20:00:00+00:00',
        completed_at_utc='2026-10-09T20:00:01+00:00',sources={},baseline_sources={},tzif=args['capture']['tzif'])
    for t in ('QQQ','SPY'):
        part=prior_observation['payload']['full_original_sources_preserved'][t]['sources']
        old=base64.b64decode(part['original_csv_bytes_base64']);new=old+b'2026-10-09,10,12,8,10,100\n'
        capture['baseline_sources'][t]=dict(bytes=old,reference=part['reference'])
        capture['sources'][t]=dict(bytes=new,reference=dict(path='next-source/'+t,sha256=sha256(new).hexdigest()))
    args['capture']=capture
    return dict(parent=parent,observation=observation_for(parent,core,args))


class CompactV4Tests(unittest.TestCase):
    def test_migrate_then_repeat_preserve_all_original_pointers_and_month(self):
        a=fixture();before=deepcopy(a);h=module.append_observation_history_v4(**a)
        self.assertEqual(a,before)
        self.assertEqual((h['typed_row_count'],h['observation_count'],h['gap_count']),(70,2,8))
        old=a['parent']['document']['history']
        for key in ('known_typed_rows','observations','parent_attempt_inventory'):
            self.assertEqual(h[key][:-1],old[key])
        self.assertEqual(h['genesis_preserved'],old['genesis_preserved'])
        self.assertEqual(h['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
        self.assertEqual(h['baseline_references'],h['accounted_baseline_references'])
        b=next_fixture(h,a['observation']);later=module.append_observation_history_v4(**b)
        self.assertEqual((later['typed_row_count'],later['observation_count'],later['gap_count']),(71,3,8))
        self.assertEqual([e['sequence']for e in later['observations']],[66,70,71])
        self.assertFalse(later['observations'][-1]['month_first_actual_observation'])
        self.assertTrue(all(later[key]is False for key in module.FLAGS))
        self.assertNotIn('original_csv_bytes_base64',str(later))

    def test_v3_view_pending_unfinished_and_scope_are_not_inferred(self):
        a=fixture();v=module.inspect_parent_history_v4(a['parent'])
        self.assertFalse(v['accounted_baseline_scope_verified']);self.assertFalse(v['source_authenticity_verified'])
        for key in ('pending_source_sessions','excluded_not_completed_source_sessions'):
            a=fixture();a['parent']['document']['history'][key]=[{'session':'2026-10-08'}]
            with self.assertRaisesRegex(ValueError,'BASELINE_HAS_UNACCOUNTED_SUFFIX'):module.append_observation_history_v4(**a)

    def test_no_omitted_duplicate_reordered_attempt_or_actual_entry(self):
        original=module.append_observation_history_v4(**fixture())
        changes=[lambda h:h['observations'].reverse(),lambda h:h['parent_attempt_inventory'].pop(),
            lambda h:h['observations'][-1].update(sequence=67),
            lambda h:h['observations'][-1]['payload_reference'].update(sha256='f'*64),
            lambda h:h['known_typed_rows'][66].update(kind='PROSPECTIVE_OBSERVED_SESSION')]
        for change in changes:
            h=deepcopy(original);change(h)
            with self.assertRaises(ValueError):module.inspect_parent_history_v4(wrap(h))

    def test_new_observation_identity_baseline_flags_counts_and_prefix(self):
        changes=[lambda a:a['observation']['payload'].update(sequence=True),
            lambda a:a['observation']['audit']['counts'].update(parent_actual_observation_count=True),
            lambda a:a['observation']['receipt'].update(future_independent_oos=0),
            lambda a:a['observation']['payload']['known_typed_rows_preserved'][0].update(seal_status='SEALED'),
            lambda a:a['observation']['payload']['parent_attempt_inventory_preserved'].clear(),
            lambda a:a['observation']['payload'].update(month_first_actual_observation=True),
            lambda a:a['observation']['payload']['full_original_sources_preserved']['QQQ']['baseline_sources'].update(reference=a['parent']['document']['history']['baseline_references']['QQQ'])]
        for change in changes:
            a=fixture();change(a)
            with self.assertRaises(ValueError):module.append_observation_history_v4(**a)

    def test_late_receipt_preserved_and_upgrade_rejected(self):
        a=fixture();o=a['observation'];o['receipt']['timing_classification']='LATE_OBSERVATION';o['audit']['counts']['timing_classification']='LATE_OBSERVATION'
        h=module.append_observation_history_v4(**a);self.assertEqual(h['observations'][-1]['timing_classification'],'LATE_OBSERVATION')
        a=fixture();a['observation']['payload']['timing_classification']='LATE_OBSERVATION'
        with self.assertRaises(ValueError):module.append_observation_history_v4(**a)

    def test_declared_rows_cannot_disagree_with_hash_bound_csv(self):
        a=fixture();a['observation']['payload']['full_original_sources_preserved']['QQQ']['sources']['rows'][-1]['Close']='11'
        with self.assertRaisesRegex(ValueError,'Raw CSV and declared rows agree'):module.append_observation_history_v4(**a)
        a=fixture();a['observation']['payload']['full_original_sources_preserved']['SPY']['baseline_sources']['rows'].pop()
        with self.assertRaises(ValueError):module.append_observation_history_v4(**a)

    def test_mandatory_false_and_source_conflict_rejected(self):
        a=fixture();del a['parent']['readback']['source_authenticity_verified']
        with self.assertRaises(ValueError):module.append_observation_history_v4(**a)
        a=fixture();a['observation']['audit']['source_hashes'][a['parent']['reference']['path']]='f'*64
        with self.assertRaisesRegex(ValueError,'Source conflict'):module.append_observation_history_v4(**a)

    def test_pure_never_reads_or_writes_paths_and_never_uses_old_append(self):
        a=fixture()
        with (patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),
              patch.object(Path,'write_bytes',side_effect=AssertionError('IO')),
              patch.object(module.compact,'append_observation_history',side_effect=AssertionError('Old V2 append'))):
            result=module.append_observation_history_v4(**a)
        self.assertEqual(result['schema'],module.SCHEMA)


if __name__=='__main__':unittest.main()
