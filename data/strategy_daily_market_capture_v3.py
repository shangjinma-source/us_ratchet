"""Keep the original two-file execution mark contract and explicit transport evidence."""
from hashlib import sha256
from datetime import datetime
import json
from core.strategy_account_ledger import require
from data.strategy_account_market_capture_v2 import StrategyAccountMarketCaptureV2


class DailyMarketCaptureV3(StrategyAccountMarketCaptureV2):
    def capture(self, **kwargs):
        result = super().capture(**kwargs)
        for mark in result['marks'].values():
            refs = mark['source_references']
            require(len(refs) == 3 and len(set(refs)) == 3
                    and set(mark['source_hashes']) == set(refs), 'DAILY_MARK_TRANSPORT_DOMAIN')
            for name in refs:
                require(sha256(result['files'][name]).hexdigest()
                        == result['source_hashes'][name] == mark['source_hashes'][name],
                        'DAILY_MARK_TRANSPORT_HASH')
            timing_path = refs[2]
            timing = json.loads(result['files'][timing_path])
            receipt = json.loads(result['files'][refs[1]])
            require(timing['schema'] == 'MARK_TRANSPORT_REAL_WAIT_V1'
                    and timing['ticker'] == mark['ticker']
                    and timing['raw_sha256'] == receipt['raw_sha256']
                    == result['source_hashes'][refs[0]]
                    and timing['raw_modified'] is False
                    and receipt['raw_path'] == refs[0]
                    and receipt['captured_at'] == mark['captured_at']
                    and datetime.fromisoformat(timing['network_received_at'])
                    <= datetime.fromisoformat(timing['verified_at'])
                    <= datetime.fromisoformat(mark['captured_at']), 'DAILY_MARK_TRANSPORT_BINDING')
            mark['transport_timing_reference'] = dict(path=timing_path,
                sha256=result['source_hashes'][timing_path])
            mark['source_references'] = refs[:2]
            mark['source_hashes'] = {name: result['source_hashes'][name] for name in refs[:2]}
        # Timing remains in the complete package and is covered by the mark hash.
        return result
