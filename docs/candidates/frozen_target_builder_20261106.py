"""Isolated trusted refresh builder; policy and quotes are server dependencies."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from core.strategy_account_ledger import canonical
from core.strategy_account_difference import require
from docs.candidates.frozen_target_provider_20261106 import FrozenTargetProvider, digest


class FrozenTargetBuilder:
    def __init__(self, *, directory, policy, contract_sha256, expected_epoch,
                 account_id, store, quote_provider, clock):
        self.directory = Path(directory)
        self.policy = deepcopy(policy)
        require(digest(self.policy) == contract_sha256, 'STRATEGY_CONTRACT_MISMATCH')
        require(self.policy['strategy_epoch'] == expected_epoch, 'STRATEGY_EPOCH_MISMATCH')
        self.contract = contract_sha256
        self.epoch = expected_epoch
        self.account_id = account_id
        self.store = store
        self.quote_provider = quote_provider
        self.clock = clock
        self.current = None
        self.versions = []

    def rebuild(self):
        # No client body is accepted here. The owning service invokes this
        # after successful cash confirmation using its trusted policy/quotes.
        require(digest(self.policy) == self.contract, 'STRATEGY_CONTRACT_MISMATCH')
        account = self.store.read()
        require(account is not None and account['account_id'] == self.account_id, 'ACCOUNT_SCOPE_MISMATCH')
        quotes = deepcopy(self.quote_provider(deepcopy(account)))
        payload = dict(schema='FROZEN_WEIGHT_TARGET_RESEARCH_V1',
            strategy_contract_sha256=self.contract,strategy_epoch=self.epoch,
            account_id=self.account_id,account_revision=account['revision'],
            weights=deepcopy(self.policy['weights']),signal_at=self.policy['signal_at'],
            valid_from=self.policy['valid_from'],valid_until=self.policy['valid_until'],
            marks=quotes['marks'],limits=quotes['limits'],
            previous_target_id=self.versions[-1]['target_id'] if self.versions else None)
        # Identical successful refresh is idempotent, but still revalidates
        # file/account/quote freshness through the current provider.
        if self.current is not None:
            current_payload = self.current._load()['payload']
            comparable = deepcopy(payload)
            comparable['previous_target_id'] = current_payload['previous_target_id']
            if comparable == current_payload:
                version = self.versions[-1]
                self.current.preview(expected_revision=account['revision'],target_id=version['target_id'],
                                     expected_proposal_id=version['proposal_id'])
                return deepcopy(version)
        target_id = digest(payload)
        document = dict(payload=payload,target_id=target_id,
            proposal_id=digest(dict(target_id=target_id,schema='FROZEN_WEIGHT_PROPOSAL_RESEARCH_V1')))
        require(self.store.read() == account, 'ACCOUNT_CHANGED_DURING_BUILD')
        self.directory.mkdir(parents=True,exist_ok=True)
        path = self.directory/(target_id+'.json')
        raw = canonical(document)
        try:
            with path.open('xb') as stream:
                stream.write(raw)
        except FileExistsError:
            require(not path.is_symlink() and path.is_file(), 'TARGET_FILE_CONFLICT')
            require(path.read_bytes() == raw, 'TARGET_FILE_CONFLICT')
        candidate = FrozenTargetProvider(path=path,file_sha256=sha256(raw).hexdigest(),
            contract_sha256=self.contract,expected_epoch=self.epoch,account_id=self.account_id,
            store=self.store,clock=self.clock)
        # Authenticate and compute once before publishing this version.
        candidate.preview(expected_revision=account['revision'],target_id=target_id,
                          expected_proposal_id=document['proposal_id'])
        record = dict(target_id=target_id,proposal_id=document['proposal_id'],
                      account_revision=account['revision'],path=str(path),sha256=sha256(raw).hexdigest())
        self.versions.append(record)
        self.current = candidate
        return deepcopy(record)

    def preview(self, **kwargs):
        require(self.current is not None, 'TARGET_NOT_BUILT')
        return self.current.preview(**kwargs)
