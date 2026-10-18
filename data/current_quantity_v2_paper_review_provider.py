"""Create-only paper-model evidence proofs; construction and frozen read never fetch."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import RLock
from data.current_quantity_v2_paper_review import (review_request,derive_paper_review,validate_paper_review,_thaw,_freeze,_checked,ERROR)
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require
from data.current_quantity_v2_difference_service import document
from data.current_research_intraday_journal import _publish

REQUEST_KEYS=('account_id','state_revision','window_start','observed_floor','securities','current_target_quantities')

class DerivedPaperReviewProvider:
    def __init__(self,*,storage_root,evidence_reader,baseline_reader=None,clock):
        self.storage_root=Path(storage_root);self.evidence_reader=evidence_reader;self.baseline_reader=baseline_reader;self.clock=clock
        self.lock=RLock();self._attempt=0;self._current=None

    def capture(self,snapshot):
        with self.lock:
            self._attempt+=1;token=self._attempt;self._current=None
        baseline=self.baseline_reader(snapshot) if self.baseline_reader else None
        request=review_request(snapshot['state'],baseline)
        action=self.evidence_reader({k:deepcopy(request[k]) for k in REQUEST_KEYS})
        review=derive_paper_review(snapshot['state'],baseline,action,self.clock())
        files={};pins={}
        for package in (baseline,action):
            if package is None:continue
            _checked(package)
            for p,raw in package['files'].items():
                require(p not in files or files[p]==raw,ERROR);files[p]=raw;pins[p]=package['source_hashes'][p]
        raw=canonical(review);h=sha256(raw).hexdigest();path='derived-paper-review/'+h+'.json'
        require(path not in files,ERROR);files[path]=raw;pins[path]=h
        result=dict(files=files,source_hashes=pins,account_review_path=path,
            shared_rss=dict(raw_path=action['documents']['rss_raw'],receipt_path=action['documents']['rss_receipt']))
        # Save immutable bytes before making this attempt available to callers.
        envelope=canonical(dict(package=_freeze(dict(files=files,source_hashes=pins,documents={
            'account_review_path':path,'shared_rss':result['shared_rss']}))))
        require(len(envelope)<=180*1024*1024,ERROR)
        saved=self.storage_root/(sha256(envelope).hexdigest()+'.json')
        _publish(saved,envelope)
        require(saved.stat().st_size==len(envelope) and saved.read_bytes()==envelope,ERROR)
        checked=self.read(snapshot,frozen_package=result)
        with self.lock:
            require(token==self._attempt,'PAPER_REVIEW_SUPERSEDED');self._current=saved
        return checked

    def read(self,snapshot,*,frozen_package=None):
        if frozen_package is None:
            with self.lock:saved=self._current
            require(saved is not None,ERROR)
            require(saved.stat().st_size<=180*1024*1024,ERROR);raw=saved.read_bytes()
            require(saved.stem==sha256(raw).hexdigest(),ERROR)
            package=_thaw(document(raw)['package']);docs=package['documents']
            result=dict(files=package['files'],source_hashes=package['source_hashes'],**docs)
        else:result=deepcopy(frozen_package)
        require(set(result)=={'files','source_hashes','account_review_path','shared_rss'},ERROR)
        _checked(dict(files=result['files'],source_hashes=result['source_hashes'],documents={}))
        review=document(result['files'][result['account_review_path']])
        validate_paper_review(review,snapshot['state'],self.clock())
        for name in ('baseline_package','action_package'):
            package=_thaw(review['derived_evidence'][name])
            if package:
                require(all(result['files'].get(p)==raw and result['source_hashes'].get(p)==package['source_hashes'][p]
                    for p,raw in package['files'].items()),ERROR)
        docs=review['derived_evidence']['action_package']['documents']
        require(result['shared_rss']==dict(raw_path=docs['rss_raw'],receipt_path=docs['rss_receipt']),ERROR)
        return deepcopy(result)
    __call__=read
