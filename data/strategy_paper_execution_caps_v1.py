"""Private temporary paper cap namespace; reuse full V2 evidence replay.

No caller-chosen path or real/legacy cap migration. This slice is not a durable
registered account; its owner must retain it for the whole review session.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from core.strategy_account_ledger import canonical, require
from backtest.current_strategy_paper_slice_v1 import replay
from data.strategy_halt_aware_pullback_cap_store_v2 import PullbackCapStore


class PaperExecutionCaps:
    def __init__(self, *, book, clock):
        verified=replay(book)
        self.account_id=verified['application']['account_id']
        self.genesis=sha256(canonical(verified['application'])).hexdigest()
        self.clock=clock
        self.namespace_id='paper-temp-cap:'+str(uuid4())
        self.directory=TemporaryDirectory(prefix='ratchet-paper-caps-')
        self.stores={}
        self.proofs=[]
        self.closed=False

    def validate(self, book):
        verified=replay(book)
        require(not self.closed and verified['application']['account_id']==self.account_id and
            sha256(canonical(verified['application'])).hexdigest()==self.genesis,'PAPER_CAP_ACCOUNT_BINDING')

    def candidate(self, **parameters):
        require(not self.closed,'PAPER_CAP_CLOSED')
        session=parameters['session']
        # The adapter validates the session; hash it rather than using it as a path.
        if session not in self.stores:
            path=Path(self.directory.name)/(sha256(session.encode()).hexdigest()+'.sqlite')
            self.stores[session]=PullbackCapStore(path,clock=self.clock,max_history_rows=10000,
                max_history_bytes=128*1024*1024,legacy_path=None)
        result=self.stores[session].candidate(**parameters)
        self.proofs.append(deepcopy(result))
        return result

    def close(self):
        self.closed=True
        self.directory.cleanup()
