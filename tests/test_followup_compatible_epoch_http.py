"""V26 current HTTP regression and emitted source references, isolated fixture."""
from hashlib import sha256
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import json
import sqlite3
from core.strategy_account_ledger import canonical
from data.strategy_unified_server_preparation_v26 import SOURCES, build_unified_server_preparation_v26
import test_completed_epoch_account_handoff_http as fixture


class FollowupEpochTests(fixture.CompletedEpochHTTPTests):
    policy_archive_root = 'data/strategy_account/test-policy'
    cap_release_bytes = canonical(dict(authorized=True, policy_id='MONTHLY_CAP50_EXIT20',
        monthly_cap='1/2', exit_ratio='4/5', sma20_overlay=False,
        authorized_at='2026-11-01T00:00:00Z', fixture_only=True))

    def advice_application(self, c, risk_reader):
        c.provider.output = risk_reader.source_reader.root/'data/strategy_account/test-execution'
        return super().advice_application(c, risk_reader)

    def extend_prepared(self, root, base):
        release_path=root/'research_contracts/cap-fixture.json'
        release_path.write_bytes(self.cap_release_bytes)
        base['observed_daily'].policy_references['cap_exit_release']=dict(
            path='research_contracts/cap-fixture.json',sha256=sha256(self.cap_release_bytes).hexdigest())
        pins = {}
        for name in SOURCES:
            body = (Path(__file__).resolve().parents[1]/name).read_bytes()
            path = root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
            pins[name] = sha256(body).hexdigest()
        config = dict(schema='FOLLOWUP_COMPATIBLE_EPOCH_PREPARATION_V26',
            base_v25=dict(path='v25.json',sha256=sha256((root/'v25.json').read_bytes()).hexdigest()),
            source_pins=pins,archive_root='data/strategy_account/test-v26')
        raw=canonical(config);(root/'v26.json').write_bytes(raw)
        with patch('data.strategy_unified_server_preparation_v26.build_unified_server_preparation_v25',return_value=base):
            result=build_unified_server_preparation_v26(root=root,configuration_path='v26.json',
                configuration_sha256=sha256(raw).hexdigest())
        self.observed=result['observed_daily']
        return result

    def verify_fill_handoff(self, c, risk_reader):
        super().verify_fill_handoff(c,risk_reader)
        with closing(sqlite3.connect(self.observed.journal.path)) as connection:
            events=[json.loads(row[0]) for row in connection.execute('SELECT body FROM advice_events')]
        ready=[event for event in events if event['response']['status']=='READY']
        self.assertTrue(ready)
        for event in ready:
            packet=self.observed.service.reader.source_reader.packet_reader
            refs=event['policy_references']['evidence_references']
            self.assertEqual(refs['review_configuration_sha256'],packet.review_reference['sha256'])
            path=Path(event['response']['evidence_archive']['receipt_path'])
            self.assertTrue(path.is_relative_to(packet.root/'data/strategy_account'))
            receipt=json.loads(path.read_bytes())
            proof=json.loads((path.parent/'sources'/(receipt['source_sha256'][receipt['cap_exit_projection_path']]+'.bin')).read_bytes())
            source=json.loads(Path(proof['source_archive']['receipt_path']).read_bytes())
            # The supplemented source uses a different archived authorization
            # shape. Record this prerequisite; this is not full follow-up admission.
            self.assertNotIn('policy_application_authorization',source)
            self.assertEqual(len([name for name in source['source_sha256']
                if name.startswith('supplement-controls/')]),1)
            self.assertEqual(len([name for name in source['source_sha256']
                if name.startswith('supplement-events/')]),1)
            from data.strategy_followup_supplement_authorization_v1 import review_supplement_authorization
            def read_reference(path, digest):
                raw=path.read_bytes()
                self.assertEqual(sha256(raw).hexdigest(),digest)
                return json.loads(raw)
            arguments=dict(root=packet.root,event=event,evidence=refs,receipt=source,
                receipt_path=Path(proof['source_archive']['receipt_path']),read_reference=read_reference)
            self.assertEqual(review_supplement_authorization(**arguments)['status'],
                'SUPPLEMENT_AUTHORIZATION_CHECKED')
            from copy import deepcopy
            wrong=deepcopy(event);wrong['account_id']='other-account'
            with self.assertRaises(ValueError):
                review_supplement_authorization(**dict(arguments,event=wrong))
            wrong=deepcopy(event);wrong['generated_at']='2000-01-01T00:00:00+00:00'
            with self.assertRaises(ValueError):
                review_supplement_authorization(**dict(arguments,event=wrong))
            for field in ('account_revision', 'target_id'):
                wrong=deepcopy(event);wrong[field]='0'*64
                with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_APPLICATION_BINDING'):
                    review_supplement_authorization(**dict(arguments,event=wrong))
            wrong_refs=deepcopy(refs);wrong_refs['trusted_release_sha256']='0'*64
            with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_AUTHORITY_RELEASE'):
                review_supplement_authorization(**dict(arguments,evidence=wrong_refs))
            from data.strategy_followup_cap_source_v2 import review_cap_event
            self.assertEqual(review_cap_event(root=packet.root,event=event)['status'],
                'CAP_ARCHIVE_AUTHORIZATION_AND_REPLAY_CHECKED')
