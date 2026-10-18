"""Fixed-target post-adoption monthly captures from accepted archive hashes.

No registry reads, research generation or capital rebinding. Caller must hold the
same source lock after paper BEGIN through commit; constructor performs no IO.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from data.current_quantity_v2_monthly_sources import QuantityV2MonthlySources
from data.current_quantity_v2_monthly_retarget import active_proposal,active_entry_policy,require_supported_monthly_entry_policy
from data.current_quantity_v2_paper_chain import build_continuation
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require,number
from data.current_research_intraday_execution import fetch_intraday_chart


class QuantityV2MonthlyContinuationSources(QuantityV2MonthlySources):
    def __init__(self,*,storage_root,monthly_blob_root,review_reader,fetch=fetch_intraday_chart,
                 clock=lambda:datetime.now(timezone.utc),pullback_policy=None,pullback_cap_store=None):
        super().__init__(storage_root=storage_root,decision_reader=None,review_reader=review_reader,fetch=fetch,clock=clock,
            pullback_policy=pullback_policy,pullback_cap_store=pullback_cap_store)
        self.monthly_blob_root=Path(monthly_blob_root)

    def _base(self,state):
        ledger=state['ledger'];active=active_proposal(ledger)
        if active_entry_policy(ledger) is not None:
            require_supported_monthly_entry_policy(ledger,self.pullback_policy)
            require(self.pullback_cap_store is not None,'PULLBACK_MONTHLY_POLICY_REQUIRED')
        require(active.get('target_scope')=='MONTHLY_CURRENT_QUOTE_ALLOCATION','ACTIVE_MONTHLY_TARGET_REQUIRED')
        require(all(o['closed'] in ('FILLED','CANCELLED','EXPIRED') for o in ledger['orders'].values())
            and number(ledger['reserved_cash'])==0 and not any(ledger['reserved_shares'].values()),'PRIOR_ORDERS_OPEN')
        causal=active['causal_inputs'];decision=causal['capital_decision'];mandate=causal['target_mandate']
        require(self._now().astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')==mandate['target_month'],'RESELECT_REQUIRED')
        require(callable(getattr(self.review_reader,'read',None)) or callable(self.review_reader),'MONTHLY_SOURCE_READER_REQUIRED')
        pins=deepcopy(causal['source_hashes']);require(len(pins)<=2000,'SOURCE_BYTES_LIMIT')
        root=self.monthly_blob_root;require(root.is_dir() and not root.is_symlink(),'MONTHLY_ORIGIN_ARCHIVE_REQUIRED')
        root=root.resolve();files={};total=0
        for name,h in pins.items():
            from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
            CurrentQuantityV2CurrentCashSources._path(name)
            require(type(h)is str and re.fullmatch('[a-f0-9]{64}',h),'MONTHLY_ORIGIN_PIN_MISMATCH')
            path=root/h;require(not path.is_symlink() and path.resolve().is_relative_to(root),'MONTHLY_ORIGIN_PATH_ESCAPE')
            require(path.is_file(),'MONTHLY_ORIGIN_BYTES_MISSING')
            size=path.stat().st_size;total+=size
            require(size<=32*1024*1024 and total<=128*1024*1024,'SOURCE_BYTES_LIMIT')
            with path.open('rb') as stream:raw=stream.read(32*1024*1024+1)
            require(len(raw)==size and sha256(raw).hexdigest()==h,'MONTHLY_ORIGIN_BYTES_CHANGED');files[name]=raw
        needed={sid for mapping in (ledger['shares'],ledger['target_quantities']) for sid,q in mapping.items() if q>0}
        require(needed<=set(causal['securities']),'COMPLETE_IDENTITY_DOMAIN_REQUIRED')
        # Preserve original identity references; these are historical byte bindings,
        # not current cash or a fresh account valuation assertion.
        identities=dict(securities={sid:deepcopy(causal['securities'][sid]) for sid in needed},
            source_references=list(decision['binding']['source_hashes']))
        documents={};prefix='generated/monthly-continuation-base/'+active['proposal_id']+'/'
        for key,value in [('capital_decision',decision),('target_mandate',mandate),('identities',identities)]:
            path=prefix+key+'.json';raw=canonical(value)
            require(path not in files or files[path]==raw,'SOURCE_PATH_CONFLICT')
            files[path]=raw;pins[path]=sha256(raw).hexdigest();documents[key]=path
        base=dict(files=files,source_hashes=pins,documents=documents)
        return base,self._identity(base),deepcopy(decision),identities,needed

    def _execution_targets(self,state,decision):
        return state['ledger']['target_quantities']

    def _validate(self,package,state):
        bridge=QuantityV2ContinuationSourceBridge(store=None,resolver=lambda *args:deepcopy(package),clock=self.clock)
        inputs,_=bridge._evidence(state,self._now())
        return build_continuation(state,execution_inputs=inputs,now=self._now())
