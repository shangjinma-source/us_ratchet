from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from data.current_research_intraday_continuity_sources import load_continuation_unit_evidence, REGISTRY
from test_current_research_intraday_execution import NOW
import test_current_research_intraday_paper_ledger as fixtures


class ContinuitySourcesTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        _, proposal, _, state = fixtures.AcceptanceTests().fixture(root/'journal')
        causal = proposal['causal_inputs']
        (root/'review.txt').write_bytes(b'Conditional synthetic unit review for test only')
        bundle = dict(schema='CONDITIONAL_INTRADAY_UNIT_REVIEW_V1', status='REVIEWED_CONDITIONAL',
                      reviewed_by='synthetic-test', account_id=state['account_id'],
                      initial_acceptance_id=state['acceptance_id'], event_path=causal['event_path'],
                      event_sha256=causal['event_sha256'],
                      source_hashes={'review.txt':sha256((root/'review.txt').read_bytes()).hexdigest()},
                      unit_continuity=dict(security_id='sndk',from_session='2026-10-15',to_session='2026-10-15',
                          initial_event_sha256=causal['event_sha256'],current_event_sha256=causal['event_sha256'],
                          status='NO_UNPROCESSED_ACTIONS',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
                          source_references=['review.txt'],covered_from=NOW.isoformat(),
                          covered_through=NOW.isoformat(),reviewed_asof=NOW.isoformat()))
        args=dict(root=root,state=state,event_path=causal['event_path'],event_sha256=causal['event_sha256'],now=NOW)
        self.save(root,bundle)
        return args,bundle

    def save(self, root, bundle):
        raw=json.dumps(bundle).encode();(root/'bundle.json').write_bytes(raw)
        entry={k:bundle[k] for k in ('account_id','initial_acceptance_id','event_path','event_sha256')}
        entry.update(bundle_path='bundle.json',sha256=sha256(raw).hexdigest())
        path=root/REGISTRY;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(dict(schema='INTRADAY_UNIT_CONTINUITY_REGISTRY_V1',entries=[entry])))

    def test_valid_pins_no_state_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            args,bundle=self.fixture(directory);before=deepcopy(args['state'])
            result=load_continuation_unit_evidence(**args)
            self.assertEqual(result['unit_continuity'],bundle['unit_continuity'])
            self.assertTrue(result['source_bytes_verified']);self.assertFalse(result['source_authenticated'])
            self.assertIn('bundle.json',result['source_hashes']);self.assertEqual(args['state'],before)

    def test_missing_registry_never_creates_it(self):
        with tempfile.TemporaryDirectory() as directory:
            args,_=self.fixture(directory);path=Path(directory)/REGISTRY;path.unlink()
            with self.assertRaisesRegex(ValueError,'NOT_REGISTERED'):load_continuation_unit_evidence(**args)
            self.assertFalse(path.exists())

    def test_changed_source_or_bundle_rejected(self):
        for name in ('review.txt','bundle.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                args,_=self.fixture(directory);(Path(directory)/name).write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):load_continuation_unit_evidence(**args)

    def test_removed_registered_source_is_not_pending_review(self):
        with tempfile.TemporaryDirectory() as directory:
            args,_=self.fixture(directory);(Path(directory)/'review.txt').unlink()
            with self.assertRaisesRegex(ValueError,'REGISTERED_SOURCE_MISSING'):
                load_continuation_unit_evidence(**args)

    def test_other_event_duplicate_and_unsafe_path_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args,_=self.fixture(directory)
            with self.assertRaisesRegex(ValueError,'NOT_FOUND'):load_continuation_unit_evidence(**dict(args,event_sha256='f'*64))
            path=Path(directory)/REGISTRY;r=json.loads(path.read_text());r['entries']*=2;path.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):load_continuation_unit_evidence(**args)
            r['entries']=r['entries'][:1];r['entries'][0]['bundle_path']='../outside.json';path.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'OUTSIDE_ROOT'):load_continuation_unit_evidence(**args)

    def test_review_time_identity_and_unpinned_references_rejected(self):
        for change in ({'reviewed_asof':'2099-01-01T00:00:00Z'}, {'security_id':'different'},
                       {'source_references':['missing']}, {'initial_event_sha256':'f'*64}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                args,bundle=self.fixture(directory);bundle['unit_continuity'].update(change);self.save(Path(directory),bundle)
                with self.assertRaises(ValueError):load_continuation_unit_evidence(**args)

    def test_cross_session_requires_action_review(self):
        with tempfile.TemporaryDirectory() as directory:
            args,bundle=self.fixture(directory);bundle['unit_continuity']['to_session']='2026-10-16';self.save(Path(directory),bundle)
            with self.assertRaisesRegex(ValueError,'ACTION_REVIEW_REQUIRED'):load_continuation_unit_evidence(**args)


if __name__=='__main__':unittest.main()
