"""Non-production, server-pinned target provider for the formal preview router."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from core.strategy_account_ledger import canonical
from core.strategy_account_difference import require, timestamp, number
from docs.candidates.target_account_bridge_20261106 import preview_target_weights


def digest(value):
    return sha256(canonical(value)).hexdigest()


class FrozenTargetProvider:
    def __init__(self, *, path, file_sha256, contract_sha256, expected_epoch, account_id, store, clock):
        self.path = Path(path)
        self.file_sha256 = file_sha256
        self.contract = contract_sha256
        self.expected_epoch = expected_epoch
        self.account_id = account_id
        self.store = store
        self.clock = clock

    def _load(self):
        require(not self.path.is_symlink(), 'TARGET_SYMLINK_REFUSED')
        raw = self.path.read_bytes()
        require(sha256(raw).hexdigest() == self.file_sha256, 'TARGET_FILE_HASH_MISMATCH')
        document = json.loads(raw)
        payload = document['payload']
        require(payload['schema'] == 'FROZEN_WEIGHT_TARGET_RESEARCH_V1', 'TARGET_SCHEMA')
        require(digest(payload) == document['target_id'], 'TARGET_HASH_MISMATCH')
        require(payload['strategy_contract_sha256'] == self.contract, 'STRATEGY_CONTRACT_MISMATCH')
        require(payload['account_id'] == self.account_id, 'ACCOUNT_SCOPE_MISMATCH')
        require(type(payload['strategy_epoch']) is str and bool(payload['strategy_epoch'].strip()), 'STRATEGY_EPOCH_REQUIRED')
        require(payload['strategy_epoch'] == self.expected_epoch, 'STRATEGY_EPOCH_MISMATCH')
        require(document['proposal_id'] == digest(dict(target_id=document['target_id'],
                    schema='FROZEN_WEIGHT_PROPOSAL_RESEARCH_V1')), 'PROPOSAL_HASH_MISMATCH')
        return document

    def preview(self, *, expected_revision, target_id, expected_proposal_id):
        document = self._load()
        require((document['target_id'], document['proposal_id']) ==
                (target_id, expected_proposal_id), 'STALE_TARGET')
        payload = document['payload']
        state = self.store.read()
        require(state is not None and state['account_id'] == self.account_id, 'ACCOUNT_SCOPE_MISMATCH')
        require(state['revision'] == expected_revision == payload['account_revision'], 'STALE_REVISION')
        now = self.clock().isoformat()
        # Validate every frozen quote, including zero-weight or unused rows,
        # before computing quantities; no unverified price enters division.
        for kind in ('marks', 'limits'):
            for sid, row in payload[kind].items():
                require(row['security_id'] == sid and row['price_basis'] == 'current', 'QUOTE_IDENTITY_MISMATCH')
                if kind == 'marks':
                    require(row.get('currency') == 'USD', 'QUOTE_CURRENCY_MISMATCH')
                age = (timestamp(now)-timestamp(row['observed_at'])).total_seconds()
                require(0 <= age <= 120, 'QUOTE_EXPIRED')
                for field in (('price',) if kind == 'marks' else ('buy','sell')):
                    try:
                        positive = number(row[field]) > 0
                    except (ValueError, ZeroDivisionError, OverflowError):
                        raise ValueError('INVALID_EXACT_QUOTE') from None
                    require(positive, 'POSITIVE_QUOTE_REQUIRED')
        result = preview_target_weights(account=state,expected_revision=expected_revision,
            weights=payload['weights'], marks=payload['marks'],limits=payload['limits'],
            signal_at=payload['signal_at'],valid_from=payload['valid_from'],
            valid_until=payload['valid_until'],now=now,contract_hash=self.contract)
        require(self._load() == document, 'TARGET_CHANGED_DURING_PREVIEW')
        require(self.store.read() == state, 'ACCOUNT_CHANGED_DURING_PREVIEW')
        checked = self.clock().isoformat()
        require(timestamp(now) <= timestamp(checked) < timestamp(payload['valid_until']), 'TARGET_EXPIRED')
        for kind in ('marks','limits'):
            require(all(0 <= (timestamp(checked)-timestamp(q['observed_at'])).total_seconds() <= 120
                        for q in payload[kind].values()), 'QUOTE_EXPIRED')
        result.update(target_id=document['target_id'],proposal_id=document['proposal_id'],
                      strategy_epoch=payload['strategy_epoch'])
        return deepcopy(result)
