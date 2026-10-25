"""Candidate V25 current HTTP route with isolated balances, fills and market."""
from hashlib import sha256
import json
from unittest.mock import patch
from core.strategy_account_ledger import canonical
import test_account_fill_advice_handoff_http as fixture
from data.strategy_unified_server_preparation_v24 import build_unified_server_preparation_v24
from data.strategy_unified_server_preparation_v25 import SOURCES, build_unified_server_preparation_v25


class CompletedEpochHTTPTests(fixture.FillHandoffHTTPTests):
    def advice_application(self, c, risk_reader):
        def mount(**arguments):
            base = build_unified_server_preparation_v24(**arguments)
            root = arguments['root']
            pins = {}
            for name in SOURCES:
                body = (fixture.fixture.fixture.ROOT/name).read_bytes()
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                pins[name] = sha256(body).hexdigest()
            packet = base['observed_daily'].service.reader.source_reader.packet_reader
            authorization = json.loads((root/packet.review_reference['path']).read_bytes())
            combined = {row['path']:row['sha256'] for row in authorization['code_pins']}
            combined.update(pins)
            authorization['code_pins'] = [dict(path=name,sha256=value) for name,value in sorted(combined.items())]
            auth_raw = canonical(authorization)
            (root/'research_contracts').mkdir(exist_ok=True)
            (root/'research_contracts/v25-authorization.json').write_bytes(auth_raw)
            config = dict(schema='COMPLETED_SELECTION_CLOSE_PREPARATION_V25',
                base_v24=dict(path=arguments['configuration_path'],
                              sha256=arguments['configuration_sha256']),
                source_pins=pins, initial_risk_epoch=dict(authorized=True, archive_root='risk-v25'),
                supplement_authorization=dict(path='research_contracts/v25-authorization.json',sha256=sha256(auth_raw).hexdigest()))
            raw = canonical(config)
            (root/'v25.json').write_bytes(raw)
            with patch('data.strategy_unified_server_preparation_v25.build_unified_server_preparation_v24',
                       return_value=base):
                prepared = build_unified_server_preparation_v25(root=root,
                    configuration_path='v25.json', configuration_sha256=sha256(raw).hexdigest())
            from data.monthly_cap_exit_reader_v4 import MonthlyCapExitReaderV4
            self.assertIsInstance(prepared['observed_daily'].service.reader, MonthlyCapExitReaderV4)
            if hasattr(self, 'extend_prepared'):
                prepared = self.extend_prepared(root, prepared)
            return prepared
        with patch('data.strategy_unified_server_preparation_v24.build_unified_server_preparation_v24',
                   side_effect=mount):
            return super().advice_application(c, risk_reader)
