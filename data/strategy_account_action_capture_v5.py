"""V3 durable capture plus separately persisted real RSS transport timing."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path

from core.strategy_account_ledger import canonical, require
from data.strategy_account_action_capture_v3 import StrategyAccountActionCaptureV3, stamp
from data.strategy_rss_verified_transport_v2 import VerifiedRssTransportV2


class StrategyAccountActionCaptureV5(StrategyAccountActionCaptureV3):
    def capture(self, request, output_directory):
        began = stamp(self.clock())
        directory = Path(output_directory)
        records = []

        def sink(evidence, raw):
            require(not records, 'RSS_TIMING_DUPLICATE')
            records.append((deepcopy(evidence), raw))

        def persist(name, raw):
            path = directory/name
            with path.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            require(path.read_bytes() == raw, 'RSS_TIMING_READBACK_FAILED')

        inner = StrategyAccountActionCaptureV3(fetch=self.fetch,
            rss_fetch=VerifiedRssTransportV2(fetch=self.rss_fetch, sink=sink, clock=self.clock),
            clock=self.clock, max_workers=self.workers)
        try:
            result = inner.capture(request, output_directory)
            require(len(records) == 1, 'RSS_TIMING_REQUIRED')
            timing, raw = records[0]
            rss_path = result['documents']['rss_raw']
            receipt_path = result['documents']['rss_receipt']
            receipt = json.loads(result['files'][receipt_path])
            require(timing['status'] == 'VERIFIED_BEFORE_CAPTURE_RETURN'
                    and raw == result['files'][rss_path]
                    and timing['raw_sha256'] == receipt['raw_sha256'] == sha256(raw).hexdigest(),
                    'RSS_TIMING_RAW_BINDING')
            require(began <= stamp(timing['transport_received_at'])
                    <= stamp(timing['verified_at']) <= stamp(receipt['received_at']),
                    'RSS_TIMING_CLOCK_ORDER')
            timing.update(capture_received_at=receipt['received_at'],
                          original_rss_receipt_path=receipt_path,
                          original_rss_receipt_sha256=result['source_hashes'][receipt_path])
            timing_raw = canonical(timing)
            digest = sha256(timing_raw).hexdigest()
            name = digest+'.json'
            persist(name, timing_raw)
            logical = 'strategy-action-capture/'+name
            require(logical not in result['files'], 'RSS_TIMING_PATH_CONFLICT')
            result['files'][logical] = timing_raw
            result['source_hashes'][logical] = digest
            require(len(result['files']) <= 2000 and
                    sum(map(len, result['files'].values())) <= 128*1024*1024,
                    'ACTION_PACKAGE_TOO_LARGE')
            # Do not change original document schema consumed by the frozen reviewer.
            finished = stamp(self.clock())
            require(finished >= stamp(receipt['received_at']) and
                    (finished-began).total_seconds() < 120, 'ACTION_WINDOW_EXPIRED')
            complete = canonical(dict(schema='ACTION_CAPTURE_V5_COMPLETE',
                status='CAPTURED_NOT_REVIEWED', source_hashes=result['source_hashes'],
                documents=result['documents'], rss_timing_path=logical,
                v3_complete_semantics='INTERNAL_STAGE_ONLY_NOT_V5_SUCCESS',
                began_at=began.isoformat(), evidence_finished_at=finished.isoformat()))
            persist('complete-v5.pending.json', complete)
            final = stamp(self.clock())
            require(final >= finished and (final-began).total_seconds() < 120,
                    'ACTION_WINDOW_EXPIRED')
            (directory/'complete-v5.pending.json').rename(directory/'complete-v5.json')
            return result
        except BaseException:
            if directory.is_dir():
                try:
                    if records:
                        evidence, raw = records[0]
                        persist('rss-timing-failed.raw', raw)
                        persist('rss-timing-failed.json', canonical(evidence))
                    persist('failed-v5.json', canonical(dict(
                        status='FAILED_PRESERVED', v3_complete_is_internal_only=True)))
                except Exception:
                    pass
            raise
