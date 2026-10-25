"""Actual V23 mounting over an isolated V22-shaped runtime.

The base runtime factory, vendor transports and authority are explicit fixtures;
V23 configuration/pins, reader construction, wrappers and HTTP routes are real.
"""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI, APIRouter
from fastapi.routing import APIRoute

from core.strategy_account_ledger import canonical
from data.strategy_daily_composition_v7 import DailyCompositionV7
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.strategy_unified_server_preparation_v23 import (
    build_unified_server_preparation_v23, SOURCES)
import test_capital_supplement_advice_http as fixture


class SourceWrapper:
    def __init__(self, packet):
        self.packet_reader = packet

    def __call__(self, *args):
        return self.packet_reader(*args)


class V23CapitalHTTPTests(fixture.CapitalAdviceHTTPTests):
    contribution_amount = '3000'

    def verify_preview_response(self, response):
        self.assertEqual(response['policy_id'],'MONTHLY_CAP50_EXIT20')
        self.assertEqual(response['observation_record']['status'],'SAVED')
        self.assertEqual(response['risk_monthly_targets']['B'],23)
        self.assertEqual(response['signal_explanations']['B']['policy'],'MONTHLY_CAP50_EXIT20')
        self.assertFalse(response['signal_explanations']['B']['exited'])

    def advice_application(self, c, risk_reader):
        packet = risk_reader.source_reader
        root = packet.root

        def put(name, value):
            raw = canonical(value)
            (root/name).write_bytes(raw)
            return dict(path=name, sha256=sha256(raw).hexdigest())

        authorization = json.loads((root/packet.review_reference['path']).read_bytes())
        old_authorization = deepcopy(authorization)
        old_authorization.pop('monthly_supplement')
        old_reference = put('v23-old-authority.json', old_authorization)
        pins = {}
        for name in SOURCES:
            raw = (fixture.fixture.ROOT/name).read_bytes()
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        authority_pins = {row['path']:row['sha256'] for row in authorization['code_pins']}
        authority_pins.update(pins)
        authorization['code_pins'] = [dict(path=name,sha256=digest)
            for name,digest in sorted(authority_pins.items())]
        new_reference = put('v23-new-authority.json', authorization)
        configuration = put('v23-server.json', dict(
            schema='MONTHLY_SUPPLEMENT_UNIFIED_PREPARATION_V23',
            base_v22=dict(path='fixture-base.json',sha256='0'*64),
            supplement_authorization=new_reference,source_pins=pins))
        # Only the prior factory is substituted; V23's actual reader constructor
        # must bind the current account/target and retain the shared risk store.
        original_review_reference = packet.review_reference
        packet.review_reference = old_reference
        risk_reader.source_reader = SourceWrapper(packet)
        daily = DailyCompositionV7(monthly_service=c.capital_monthly,
            evidence_reader=risk_reader,execution_provider=c.provider.execution,
            clock=lambda:c.clock[0],policy_execution_enabled=True,
            policy_id='MONTHLY_CAP50_EXIT20',fee_bps='10')
        journal = DailyAdviceJournalV1(root/'v23-advice.sqlite',clock=lambda:c.clock[0])
        old = SimpleNamespace(service=SimpleNamespace(service=daily),journal=journal,
            clock=lambda:c.clock[0],policy_references={'fixture':'base'})
        router = APIRouter()
        async def unused():
            raise AssertionError('V23 must replace the old preview route')
        router.add_api_route('/api/strategy-daily-v3/preview',unused,methods=['POST'])
        async def health():
            return {'status':'fixture'}
        router.add_api_route('/fixture-health',health,methods=['GET'])
        retained = router.routes[-1]
        base = dict(monthly=c.capital_monthly,observed_daily=old,router=router,
            validate_code=c.capital_monthly.validate_current_target_pins)
        with patch('data.strategy_unified_server_preparation_v23.build_unified_server_preparation_v22',
                return_value=base) as factory:
            prepared = build_unified_server_preparation_v23(root=root,
                configuration_path=configuration['path'],configuration_sha256=configuration['sha256'])
        packet.review_reference = original_review_reference
        factory.assert_called_once()
        observed = prepared['observed_daily']
        self.assertIs(observed.journal,journal)
        self.assertIs(observed.monthly,c.capital_monthly)
        built = observed.service.reader
        self.assertIs(built.risk_store,risk_reader.risk_store)
        new_packet = built.source_reader.packet_reader
        self.assertEqual(new_packet.account_reader(),c.store.read())
        self.assertEqual(new_packet.target_reader(),c.capital_monthly.current())
        new_packet.fetch_daily = packet.fetch_daily
        new_packet.fetch_official = packet.fetch_official
        self.assertIn(retained,prepared['router'].routes)
        self.assertEqual(sum(isinstance(route,APIRoute) and
            route.path=='/api/strategy-daily-v3/preview'
            for route in prepared['router'].routes),1)
        app = c.capital_application
        app.include_router(prepared['router'])
        return app
