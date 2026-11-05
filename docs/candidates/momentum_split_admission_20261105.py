"""Exact six-event research mapping. Does not change prices or authorize other actions."""
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MAPPING='tmp/momentum_split_mapping_20261105/mapping.json'
EXPECTED='6dc917e61e9b2d74e0e104659f3f9627800a6a79d24c631215d05f0900d0f1f0'


def require(ok,reason):
    if not ok:raise ValueError(reason)


class FixedSplitAdmission:
    def __init__(self):
        raw=(ROOT/MAPPING).read_bytes();require(sha256(raw).hexdigest()==EXPECTED,'SPLIT_MAPPING_CHANGED')
        artifact=json.loads(raw)
        require(artifact['schema']=='FIXED_MOMENTUM_SPLIT_MAPPING_V1' and len(artifact['records'])==6,'SPLIT_MAPPING_SCHEMA')
        self._records=artifact['records'];self.source_hashes={MAPPING:EXPECTED,**artifact['source_hashes']}
        self.verify_sources()

    def verify_sources(self):
        for name,digest in self.source_hashes.items():
            path=(ROOT/name).resolve();require(path.is_relative_to(ROOT),'SPLIT_SOURCE_PATH')
            require(sha256(path.read_bytes()).hexdigest()==digest,'SPLIT_SOURCE_CHANGED:'+name)

    def _selected(self,window):
        require(window in ('2021_2023','2024_2026'),'SPLIT_WINDOW')
        return [r for r in self._records if r['window']==window]

    def _paired(self,document,event):
        key=(event['security_id'],event['date'])
        for field in ('actions','provider_actions'):
            matches=[e for e in document['assembled'][field] if (e['security_id'],e['date'])==key]
            require(matches==[event],'SPLIT_EXECUTION_PAIR_REQUIRED:'+field)

    def install(self,document,window):
        result=deepcopy(document)
        for record in self._selected(window):
            event=record['event'];key=(event['security_id'],event['date'])
            existing=[[e for e in result['assembled'][field] if (e['security_id'],e['date'])==key] for field in ('actions','provider_actions')]
            if existing==[[],[]]:
                require(not record['already_present'],'PREEXISTING_SMCI_MISSING')
                for field in ('actions','provider_actions'):result['assembled'][field].append(deepcopy(event))
            else:self._paired(result,event)
            for check in record['coordinate_checks']:
                require(result['ohlc'][check['security_id']][check['date']][check['field']]==check['nominal'],'NOMINAL_QUOTE_CHANGED')
            self._paired(result,event)
        for field in ('actions','provider_actions'):
            result['assembled'][field].sort(key=lambda e:(e['date'],e['security_id'],e['type']))
        return result

    def admit(self,gate,document,window):
        result=deepcopy(gate);accepted=[];remaining=[]
        for observed in result['unmapped_events']:
            matches=[r for r in self._selected(window) if observed in r['observed_provider_events']]
            if not matches:
                remaining.append(observed);continue
            require(len(matches)==1,'AMBIGUOUS_SPLIT_EVIDENCE')
            record=matches[0];self._paired(document,record['event'])
            accepted.append(dict(provider_event=observed,execution_event=record['event'],official_evidence=record['official_evidence'],
                                 scope='EXACT_EVENT_MAPPING_REQUIRES_ACCOUNT_AND_RISK_BRIDGE'))
        result.update(unmapped_events=remaining,mapped_fixed_splits=accepted,admitted=not remaining and not result['missing_action_streams'])
        return result
