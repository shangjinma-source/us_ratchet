"""Request-local display batch; two shared snapshots, no lock across transport.

Not mounted automatically. Each member retains the existing unit, time, source
and identity checks. A failed member breaks the final rendezvous for all members.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

from core.strategy_account_ledger import require
from data.strategy_frontier_latest_display_charts_v1 import frontier_display_context
from data.strategy_latest_display_charts_v1 import LatestDisplayChartsV1


class FrontierDisplayBatchV1:
    def __init__(self, *, view, **display_options):
        self.view = view
        self.display_options = display_options

    def bars(self, *, security_ids, expected_proposal_id, interval="day", bars=90):
        require(type(security_ids) is list and 1 <= len(security_ids) <= 8
                and all(type(value) is str and value for value in security_ids)
                and len(set(security_ids)) == len(security_ids)
                and interval in ("day", "week", "month")
                and type(bars) is int and 1 <= bars <= 260,
                "DISPLAY_BATCH_ARGUMENTS")
        identifiers = tuple(security_ids)

        def contexts():
            # Nested resolver calls reuse this operation's snapshot. The lock
            # is released before fetch and reacquired only for the final read.
            with self.view.monthly.snapshot_operation():
                return {identifier: frontier_display_context(
                    self.view, identifier, expected_proposal_id)
                    for identifier in identifiers}

        self.display_options["validate_sources"]()
        initial = contexts()
        final = {}

        def verify_batch():
            self.display_options["validate_sources"]()
            current = contexts()
            require(current == initial, "DISPLAY_SNAPSHOT_CHANGED")
            final.update(current)

        rendezvous = Barrier(len(identifiers), action=verify_batch, timeout=30)

        def member(identifier):
            reads = 0

            def context_reader(requested):
                nonlocal reads
                require(requested == identifier, "DISPLAY_CONTEXT_BINDING")
                reads += 1
                require(reads <= 2, "DISPLAY_BATCH_CONTEXT_READS")
                if reads == 1:
                    return deepcopy(initial[identifier])
                rendezvous.wait()
                return deepcopy(final[identifier])

            try:
                service = LatestDisplayChartsV1(context_reader=context_reader,
                                               **self.display_options)
                result = service.bars(security_id=identifier, interval=interval, bars=bars)
                result["proposal_id"] = expected_proposal_id
                return result
            except BaseException:
                rendezvous.abort()
                raise

        # All workers must exist before awaiting one, otherwise the barrier
        # would wait on a member that has not been scheduled.
        with ThreadPoolExecutor(max_workers=len(identifiers),
                                thread_name_prefix="display-batch") as pool:
            futures = [pool.submit(member, identifier) for identifier in identifiers]
            results = [future.result() for future in futures]
        return dict(status="DISPLAY_ONLY", proposal_id=expected_proposal_id,
                    charts=results, executable=False, training_modified=False)
