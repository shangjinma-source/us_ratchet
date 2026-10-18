"""Exact issuer-aware combination indexing, never a risk-feasibility assertion.

ISSUER_SID_PREFIX_LEX_V1 sorts issuer IDs and each issuer's explicit security IDs
by Python string code-point order. A selection is a tuple of (issuer, security)
pairs with strictly increasing issuers; selections are ordered lexicographically
by that pair tuple. This is not the legacy group-combinations/product ordering.
"""
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType

ORDER_VERSION='ISSUER_SID_PREFIX_LEX_V1'
MAX_SLICE_SIZE=10000
STATUS='ENUMERATED_ONLY_NOT_RISK_FEASIBILITY'


def require(ok,message):
    if not ok:raise ValueError(message)


def text(value):
    require(type(value) is str and bool(value) and value==value.strip(),'Nonempty canonical explicit ID required')
    return value


def integer(value):
    require(type(value) is int,'Exact integer required; booleans are not coordinates')
    return value


@dataclass(frozen=True,init=False)
class IssuerCombinationIndex:
    """Immutable DP index built from a sequence of (issuer_id, security_ids).

    A sequence is deliberate: duplicate issuer declarations cannot be silently
    overwritten by a dictionary. IDs carry no authenticated identity semantics.
    Only slice() enumerates outputs, and only within its explicit bounded range.
    """
    issuer_ids:tuple
    security_groups:tuple
    group_fingerprint:str
    _counts:tuple
    _locations:object

    def __init__(self,groups):
        require(type(groups) in (list,tuple) and bool(groups),'Nonempty explicit issuer-group sequence required')
        seen_issuers=set();seen_securities=set();normalized=[]
        for entry in groups:
            require(type(entry) in (list,tuple) and len(entry)==2,'Issuer and security-list pair required')
            issuer=text(entry[0]);securities=entry[1]
            require(issuer not in seen_issuers,'Duplicate issuer group')
            require(type(securities) in (list,tuple) and bool(securities),'Each issuer requires a nonempty security list')
            members=[]
            for security in securities:
                sid=text(security);require(sid not in seen_securities,'Duplicate security ID within or across issuers')
                seen_securities.add(sid);members.append(sid)
            seen_issuers.add(issuer);normalized.append((issuer,tuple(sorted(members))))
        normalized.sort(key=lambda pair:pair[0]);issuers=tuple(pair[0] for pair in normalized)
        members=tuple(pair[1] for pair in normalized);n=len(issuers)
        counts=[[0]*(n+1) for _ in range(n+1)];counts[n][0]=1
        for i in range(n-1,-1,-1):
            counts[i][0]=1
            for k in range(1,n-i+1):counts[i][k]=counts[i+1][k]+len(members[i])*counts[i+1][k-1]
        payload={'order_version':ORDER_VERSION,'groups':normalized}
        fingerprint=hashlib.sha256(json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        object.__setattr__(self,'issuer_ids',issuers);object.__setattr__(self,'security_groups',members)
        object.__setattr__(self,'group_fingerprint',fingerprint);object.__setattr__(self,'_counts',tuple(tuple(row) for row in counts))
        object.__setattr__(self,'_locations',MappingProxyType({sid:(i,j) for i,group in enumerate(members) for j,sid in enumerate(group)}))

    def _k(self,k):
        integer(k);require(1<=k<=len(self.issuer_ids),'Public k must be 1..issuer_count')
        return k

    def count(self,k):
        return self._counts[0][self._k(k)]

    def counts_by_k(self):
        return {k:self._counts[0][k] for k in range(1,len(self.issuer_ids)+1)}

    def unrank(self,k,position):
        remaining=self._k(k);integer(position)
        require(0<=position<self.count(k),'Rank outside combination count')
        lower=0;selected=[]
        while remaining:
            for issuer in range(lower,len(self.issuer_ids)-remaining+1):
                suffix=self._counts[issuer+1][remaining-1]
                block=len(self.security_groups[issuer])*suffix
                if position>=block:position-=block;continue
                security_index,position=divmod(position,suffix)
                selected.append(self.security_groups[issuer][security_index])
                lower=issuer+1;remaining-=1
                break
            else:raise AssertionError('DP index failed to locate a valid rank')
        return tuple(selected)

    def rank(self,k,selection):
        remaining=self._k(k)
        require(type(selection) in (list,tuple) and len(selection)==k,'Exact canonical selection length required')
        locations=[]
        for sid in selection:
            text(sid);require(sid in self._locations,'Unknown security ID')
            locations.append(self._locations[sid])
        require(all(a[0]<b[0] for a,b in zip(locations,locations[1:])),
                'Selection must have strictly increasing issuers; no sorting or issuer duplicates')
        lower=0;position=0
        for issuer,security_index in locations:
            for skipped in range(lower,issuer):
                position+=len(self.security_groups[skipped])*self._counts[skipped+1][remaining-1]
            position+=security_index*self._counts[issuer+1][remaining-1]
            lower=issuer+1;remaining-=1
        require(position<self.count(k),'Canonical selection rank differs')
        return position

    def slice(self,k,start,stop,*,max_slice_size):
        total=self.count(k);integer(start);integer(stop);integer(max_slice_size)
        require(1<=max_slice_size<=MAX_SLICE_SIZE,'Explicit slice budget must be 1..10000')
        require(0<=start<=stop<=total,'Half-open slice outside combination count')
        require(stop-start<=max_slice_size,'Requested slice exceeds explicit budget')
        # Skip preceding blocks arithmetically; no full combination list exists.
        combinations=[self.unrank(k,position) for position in range(start,stop)]
        return dict(order_version=ORDER_VERSION,group_fingerprint=self.group_fingerprint,
            issuer_count=len(self.issuer_ids),security_count=len(self._locations),k=k,total_count=total,
            start=start,stop=stop,returned_count=len(combinations),max_slice_size=max_slice_size,
            status=STATUS,combinations=combinations,risk_feasibility_evaluated=False,
            identities_authenticated=False,task_identity_generated=False,fit_performed=False)
