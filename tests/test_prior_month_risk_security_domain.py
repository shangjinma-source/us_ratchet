"""Verify closed positions remain in the source domain, never in holdings."""
from copy import deepcopy
import test_strategy_monthly_supplement_reader as fixture
from data.strategy_monthly_risk_security_domain_v1 import plan_risk_security_domain


class PriorMonthRiskDomainTests(fixture.SupplementReaderTests):
    def verify_fill_handoff(self, c, risk_reader):
        from data.strategy_daily_security_domain_v1 import locate_unit_baseline_sources
        import json
        target = c.target
        prior = risk_reader.risk_store.read(c.store.read()['account_id'])
        prior = deepcopy(prior)
        prior['decision_date'] = '2026-10-30'  # Isolated prior-month risk fixture.
        held = c.store.read()
        quantity = held['shares']['A']
        self.assertGreater(quantity, 0)
        c.store.append(dict(event_id='risk-domain-sell', kind='DIRECT_FILL',
            security_id='A', side='SELL', quantity=quantity, price='100', fees='0',
            executed_at=c.clock[0].isoformat()), expected_revision=held['revision'])
        state = c.store.read()
        source = json.loads((risk_reader.source_reader.root / risk_reader.source_reader.reference['path']).read_bytes())
        paths = locate_unit_baseline_sources(root=risk_reader.source_reader.root,
            evidence_root=source['target_evidence_root'],
            binding=target['payload']['decision']['payload']['input_binding'])
        arguments=dict(root=risk_reader.source_reader.root, state=state, target=target,
            identity_reference=c.identity_reference, source_paths=paths, risk_state=prior)
        result = plan_risk_security_domain(**arguments)
        self.assertIn('A', result['securities'])
        self.assertIn('MONTHLY_RISK_TRACKING', result['securities']['A']['reasons'])
        self.assertNotIn('ACTUAL_HOLDING', result['securities']['A']['reasons'])
        self.assertEqual(c.store.read(), state)
        from hashlib import sha256
        from data.strategy_daily_first_window_v7 import SOURCES
        from data.strategy_monthly_risk_capture_v2 import (
            prepare_risk_supplement_request, capture_supplement, review_risk_supplement_packets)
        root = risk_reader.source_reader.root
        pins = []
        for name in SOURCES:
            raw = (fixture.ROOT/name).read_bytes()
            path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            pins.append(dict(path=name, sha256=sha256(raw).hexdigest()))
        prepared = prepare_risk_supplement_request(root=root, state=state, target=target,
            identity_reference=c.identity_reference, calendar_reference=source['calendar'],
            unit_source_paths=paths, source_pins=pins, security_ids={'A'},
            decision_date=prior['decision_date'], now=c.clock[0], risk_state=prior)
        self.assertEqual(prepared['status'], 'SUPPLEMENT_REQUEST_PREPARED')
        capture = capture_supplement(directory=root/'risk-only-capture',
            request=prepared['request'], binding=prepared['binding'],
            read_binding=lambda:prepared['binding'], execute=True, clock=lambda:c.clock[0],
            fetch_daily=risk_reader.source_reader.fetch_daily,
            fetch_official=risk_reader.source_reader.fetch_official)
        reviewed = review_risk_supplement_packets(root=root, capture=capture,
            request=prepared['request'], binding=prepared['binding'], state=state, target=target,
            configurations=prepared['configurations'], risk_state=prior, clock=lambda:c.clock[0])
        packet = reviewed['packets']['A']; receipt=json.loads(packet['receipt_bytes'])
        inputs=json.loads(packet['files'][receipt['monthly_history_inputs_path']])
        self.assertEqual(set(inputs['histories']), {'A'})
        self.assertEqual(inputs['base_target']['quantities']['A'], 0)
        self.assertEqual(c.store.read(), state)
        changed_capture=deepcopy(capture)
        name=next(iter(changed_capture['files']))
        changed_capture['files'][name]+=b' '
        with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_SOURCE_CHANGED'):
            review_risk_supplement_packets(root=root, capture=changed_capture,
                request=prepared['request'], binding=prepared['binding'], state=state, target=target,
                configurations=prepared['configurations'], risk_state=prior, clock=lambda:c.clock[0])
        changed_risk=deepcopy(prior);changed_risk['peaks']['A']='999'
        with self.assertRaisesRegex(ValueError, 'RISK_REVIEW_STATE_CHANGED'):
            review_risk_supplement_packets(root=root, capture=capture,
                request=prepared['request'], binding=prepared['binding'], state=state, target=target,
                configurations=prepared['configurations'], risk_state=changed_risk, clock=lambda:c.clock[0])
        for field, value in [('account_id','another-account'), ('target_month','2000-01')]:
            changed = deepcopy(prior); changed[field] = value
            with self.assertRaisesRegex(ValueError, 'RISK_DOMAIN_BINDING'):
                plan_risk_security_domain(**dict(arguments, risk_state=changed))
