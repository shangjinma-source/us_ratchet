import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.preflight_prospective_paper_sources_v1 import preflight, Inventory


class PreflightTests(unittest.TestCase):
    def fixture(self, root):
        def save(name, value):
            raw=json.dumps(value).encode();(root/name).write_bytes(raw)
            return dict(path=name,sha256=sha256(raw).hexdigest())
        evidence=save('evidence.json',{'fixture':True})
        identity=save('identity.json',dict(candidates=[dict(ticker='A',security_id='sid:A',
            status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['evidence.json'])],
            source_hashes={'evidence.json':evidence['sha256']}))
        training=save('training.json',dict(candidates=[dict(ticker='A',security_id='sid:A',raw_close=['1']*253)],
            decision_date='2026-10-14',source_hashes={'evidence.json':evidence['sha256']},full_pit_verified=False))
        calendar=save('calendar.json',dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',
            sessions=[dict(date='2026-10-23',open='2026-10-23T13:30:00Z',close='2026-10-23T20:00:00Z')]))
        inputs=save('inputs.json',dict(signal_date='2026-10-22',histories={'sid:A':{}}))
        receipt=save('receipt.json',dict(normalization_reviewed=True,unresolved_units=[],pending_rights=[],
            source_sha256={'inputs.json':inputs['sha256']},normalized_inputs_path='inputs.json'))
        manifest=save('manifest.json',{'inputs.json':inputs})
        terminal=save('terminal.json',dict(status='DYNAMIC_DOMAIN_PACKET_SAVED',finished_at='2026-10-22T14:00:00Z',
            session='2026-10-22',packets={'sid:A':dict(receipt_reference=receipt,manifest_reference=manifest)}))
        return dict(training=training,identity=identity,calendar=calendar,daily_terminals=[terminal],expected_candidate_count=1)

    def test_inventory_does_not_turn_saved_sources_into_paper_authority(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);request=self.fixture(root)
            before={p.name:p.read_bytes() for p in root.iterdir()}
            result=preflight(root=root,request=request,now='2026-10-23T13:00:00Z')
            self.assertEqual(result['missing_daily_parent_tickers'],[])
            self.assertTrue(result['securities'][0]['identity_ok'])
            self.assertFalse(result['securities'][0]['daily_parent_candidates'][0]['paper_registered'])
            self.assertEqual(result['next_future_window']['accept_from'],'2026-10-23T14:00:00+00:00')
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})
            self.assertFalse(result['book_created']);self.assertEqual(result['network_calls'],0)

    def test_corrupt_parent_blob_reports_missing_instead_of_available(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);request=self.fixture(root);(root/'inputs.json').write_bytes(b'{}')
            result=preflight(root=root,request=request,now='2026-10-23T13:00:00Z')
            self.assertEqual(result['missing_daily_parent_tickers'],['A'])
            self.assertTrue(result['parent_errors'])

    def test_identity_source_corruption_and_count_mismatch_block(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);request=self.fixture(root);request['expected_candidate_count']=98
            (root/'evidence.json').write_bytes(b'{}')
            result=preflight(root=root,request=request,now='2026-10-23T13:00:00Z')
            self.assertFalse(result['securities'][0]['identity_ok'])
            self.assertTrue(result['source_errors'])
            self.assertIn('CANDIDATE_COUNT_MISMATCH',result['blockers'])

    def test_no_past_first_window_or_path_escape(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);request=self.fixture(root)
            result=preflight(root=root,request=request,now='2026-10-23T14:00:01Z')
            self.assertIsNone(result['next_future_window'])
            with self.assertRaisesRegex(ValueError,'PREFLIGHT_PATH'):
                Inventory(root).read(dict(path='../outside',sha256='0'*64))

    def test_saved_unit_baseline_only_allows_future_first_window_review(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);request=self.fixture(root);request['daily_terminals']=[]
            review=dict(schema='STRATEGY_TARGET_UNIT_REVIEW_V1',status='CONDITIONAL_CURRENT_UNITS_REVIEWED',
                training_manifest_sha256=request['training']['sha256'],unresolved=[],pending_rights=[],
                reviewed_at='2026-10-22T14:00:00Z',securities={'sid:A':dict(
                    training_manifest_sha256=request['training']['sha256'],covered_through='2026-10-22T14:00:00Z',
                    source_references=['evidence.json'])})
            raw=json.dumps(review).encode();(root/'unit.json').write_bytes(raw)
            request['unit_baseline']=dict(review_reference=dict(path='unit.json',sha256=sha256(raw).hexdigest()),
                source_mapping={'evidence.json':dict(path='evidence.json',sha256=sha256((root/'evidence.json').read_bytes()).hexdigest())})
            result=preflight(root=root,request=request,now='2026-10-23T13:00:00Z')
            self.assertEqual(result['preparation_counts'],{'AUTO_CAPTURE_AND_FIRST_WINDOW_REVIEW_REQUIRED':1})
            self.assertFalse(result['securities'][0]['saved_unit_baseline']['current_units_verified'])
            self.assertFalse(result['first_parent_implementation']['already_executed'])
            (root/'evidence.json').write_bytes(b'{}')
            result=preflight(root=root,request=request,now='2026-10-23T13:00:00Z')
            self.assertTrue(result['baseline_errors'])
            self.assertEqual(result['preparation_counts'],{'INDEPENDENT_SOURCE_REPAIR_REQUIRED':1})


if __name__=='__main__':unittest.main()
