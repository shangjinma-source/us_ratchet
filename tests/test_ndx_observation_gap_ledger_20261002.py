from copy import deepcopy
import csv
import io
import json
import unittest
from scripts import ndx_observation_gap_ledger_20261002 as module


def encoded(value): return json.dumps(value).encode()


def csv_bytes(rows):
    stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows); return stream.getvalue().encode()


def fixture():
    raw={
        'parent_events':b''.join(encoded({'event_sha256':'a'*64})+b'\n' for _ in range(66)),
        'parent_sessions':csv_bytes([{'session_date':'2026-09-24'} for _ in range(60)])}
    source_rows=[{'Date':day,'Open':'1','High':'2','Low':'1','Close':'2','Volume':'100'} for day in module.DATES]
    raw.update(QQQ=csv_bytes(source_rows),SPY=csv_bytes(source_rows))
    refs={key:{'path':'synthetic/'+key,'sha256':module.sha(value)} for key,value in raw.items()}
    manifest={'manifest_type':'ndx_observed_us_session_calendar_v2','event_count':66,'session_count':60,
        'decision_eligible_session_count':0,'latest_session_date':'2026-09-24','latest_event_sha256':'a'*64,
        'commit_transaction_id':'c'*64,'artifacts':{'event_ledger':refs['parent_events'],'session_projection':refs['parent_sessions']}}
    raw['parent_manifest']=encoded(manifest)
    refs['parent_manifest']={'path':'synthetic/parent_manifest','sha256':module.sha(raw['parent_manifest'])}
    raw['parent_receipt']=encoded({'transaction_id':'c'*64,'planned_manifest':manifest})
    capture={'schema':'CURRENT_SOURCE_GAP_CLASSIFICATION_CAPTURE_V1','captured_using_system_clock':True,
        'parent_references':{'calendar_manifest':refs['parent_manifest'],'calendar_events':refs['parent_events']},
        'classification':{'pending_classifications':[{'session':day} for day in module.DATES],
                          'timeliness_candidate':None,'missed_or_ineligible_row_count':5},
        'captured_source_references':{ticker:refs[ticker] for ticker in ('QQQ','SPY')},
        'pending_source_rows':{ticker:{row['Date']:row for row in source_rows} for ticker in ('QQQ','SPY')},
        **dict.fromkeys(('calendar_append_allowed','candidate_seal_allowed','cohort_registration_allowed',
            'old_calendar_mutated','source_price_rows_validated_for_execution','promotion_allowed','live_mutation_allowed'),False)}
    raw['classification']=encoded(capture)
    refs.update({key:{'path':'synthetic/'+key,'sha256':module.sha(raw[key])} for key in ('classification','parent_receipt')})
    return raw,refs


class PreparationTests(unittest.TestCase):
    def test_prepare_copies_binding_without_reclassifying(self):
        raw,refs=fixture(); original=deepcopy(raw); prepared=module.prepare(raw,refs)
        self.assertEqual(prepared['parent_binding']['event_count'],66)
        self.assertEqual(prepared['parent_binding']['session_count'],60)
        self.assertEqual(prepared['classification_capture'],json.loads(raw['classification']))
        self.assertEqual(raw,original)

    def test_reject_receipt_or_parent_prefix_drift(self):
        for role in ('parent_receipt','parent_events','parent_sessions'):
            raw,refs=fixture()
            if role=='parent_receipt':
                value=json.loads(raw[role]); value['transaction_id']='d'*64; raw[role]=encoded(value)
            elif role=='parent_events': raw[role]+=b'{}\n'
            else: raw[role]=csv_bytes([{'session_date':'2026-09-23'} for _ in range(60)])
            with self.subTest(role=role),self.assertRaises(ValueError): module.prepare(raw,refs)

    def test_reject_capture_authority_or_saved_row_change(self):
        for change in ('permission','price','dates'):
            raw,refs=fixture(); value=json.loads(raw['classification'])
            if change=='permission': value['candidate_seal_allowed']=True
            elif change=='price': value['pending_source_rows']['QQQ'][module.DATES[0]]['Close']='99'
            else: value['classification']['pending_classifications'].pop()
            raw['classification']=encoded(value)
            with self.subTest(change=change),self.assertRaises(ValueError): module.prepare(raw,refs)


if __name__=='__main__': unittest.main()
