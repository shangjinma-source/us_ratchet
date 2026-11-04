"""Versioned faster snapshot replay; original adoption and account locks retained."""
from datetime import datetime
from pathlib import Path
from hashlib import sha256
from core.strategy_account_ledger import apply_event, create_account, require
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation as Original, SNAPSHOT_FIELDS
from data.strategy_profiled_ready_release_replayed_v1 import validate_ready_release

SOURCES = {
    'data/strategy_sized_read_v1.py',
    'data/strategy_account_unit_review_compiled_v1.py',
    'data/strategy_compiled_notice_review_v1.py',
    'data/strategy_monthly_file_sized_v1.py',
    'data/strategy_account_monthly_release_sized_v1.py',
    'data/strategy_account_ready_release_sized_v1.py',
    'data/strategy_profiled_monthly_release_sized_v1.py',
    'data/strategy_profiled_ready_release_sized_v1.py',
    'data/strategy_profiled_release_snapshot_sized_v1.py',
}

SOURCES |= {'data/strategy_release_replay_cache_v1.py', 'data/strategy_profiled_monthly_release_replayed_v1.py', 'data/strategy_profiled_release_snapshot_replayed_v1.py', 'data/strategy_account_monthly_release_replayed_v1.py', 'data/strategy_replayed_snapshot_install_v1.py', 'data/strategy_account_ready_release_replayed_v1.py', 'data/strategy_profiled_ready_release_replayed_v1.py'}

class ProfiledMonthlyReleaseActivation(Original):
    def __init__(self, *, reader_source_pins, validate_code, **kwargs):
        require(type(reader_source_pins) is dict and set(reader_source_pins) == SOURCES,
                'SIZED_READER_APPROVED_PINS_REQUIRED')
        pins = dict(reader_source_pins)
        root = Path(kwargs['root']).resolve()
        executing = Path(__file__).resolve().parents[1]
        def gate():
            validate_code()
            for name, expected in pins.items():
                for base in (root, executing):
                    path = base/name
                    require(not path.is_symlink() and path.resolve().is_relative_to(base), 'SIZED_READER_LINK_REFUSED')
                    require(sha256(path.read_bytes()).hexdigest() == expected, 'SIZED_READER_SOURCE_CHANGED')
        gate()
        super().__init__(validate_code=gate, **kwargs)

    def _validate_saved(self, active):
        """Replay admission at adoption time, without treating it as fresh data.

        The account may legitimately have changed since adoption. Its verified
        journal must still contain the exact revision reviewed by this receipt.
        Current-month and execution freshness checks remain the router's job.
        """
        payload = active['payload']
        adopted = datetime.fromisoformat(payload['adopted_at'])
        now = self.clock()
        require(isinstance(now, datetime) and now.utcoffset() is not None
                and adopted.utcoffset() is not None and adopted <= now,
                'ACTIVATION_SAVED_CLOCK_INVALID')
        state = self.accounts.read()
        require(state is not None, 'ACCOUNT_NOT_INITIALIZED')
        historical = create_account(state['account_id'])
        for event in state['events']:
            if historical['revision'] == payload['account_revision']:
                break
            historical, _ = apply_event(historical, event['payload'], expected_revision=historical['revision'])
        require(historical['revision'] == payload['account_revision'],
                'ACTIVATION_SAVED_ACCOUNT_REVISION_MISSING')
        reviewed = validate_ready_release(root=self.root, receipt_path=payload['ready_path'],
            receipt_sha256=payload['ready_sha256'], account_state=historical, clock=lambda:adopted)
        require(all(reviewed[name] == payload[name] for name in SNAPSHOT_FIELDS)
                and reviewed['configuration']['target_month'] == payload['target_month']
                and reviewed['account_revision'] == payload['account_revision'],
                'ACTIVATION_SAVED_RECEIPT_BINDING_MISMATCH')
        self.gate()
        return reviewed
