"""Reference-only coverage: never passes synthetic scope quantities to selector."""
from copy import deepcopy
from fractions import Fraction as F


def need(ok,why):
    if not ok:raise ValueError(why)

class ReferenceCoverage:
    def __init__(self,*,window,document,prices,review,source_validator,legacy_absence=None,reference_cash_review=None,root=None):
        need(callable(source_validator),'PINNED_INPUT_VALIDATOR_REQUIRED')
        source_validator() # caller authenticates complete input/review/source closure
        self.window=window;self.doc=document;self.prices=prices;self.review=review
        self.legacy_absence=legacy_absence
        self.cash_review=reference_cash_review or {'rows':[]}
        if reference_cash_review:
            from pathlib import Path
            from hashlib import sha256
            need(root is not None,'REFERENCE_CASH_ROOT_REQUIRED')
            for path,digest in reference_cash_review['source_hashes'].items():need(sha256((Path(root)/path).read_bytes()).hexdigest()==digest,'REFERENCE_CASH_SOURCE_CHANGED')
        self.domain=document['assembled'];self.actions=self.domain['actions']
        self.audit=[]

    def __call__(self,lock,end,buy_sids):
        old=lock['security_id'];start=lock['exit_date'];sid=old
        conversions=[]
        for a in sorted(self.actions,key=lambda x:x['date']):
            if start<a['date']<=end and a['security_id']==sid:
                # Only the already reviewed ordinary integer SMCI transition.
                need(set(a)=={'type','date','security_id','new_security_id','old_shares','new_shares','source_references'},'REFERENCE_EXACT_REVIEWED_SPLIT_SCHEMA')
                need(a['type']=='split_identity' and a['date']=='2024-10-01' and sid=='security:0001375365:86800U104' and a['new_security_id']=='security:0001375365:86800U302' and F(a['old_shares'])==1 and F(a['new_shares'])==10 and a['source_references'],'REFERENCE_UNSUPPORTED_ACTION')
                conversions.append(dict(date=a['date'],old_sid=sid,new_sid=a['new_security_id'],ratio='10',kind='REVIEWED_INTEGER_SPLIT',source_references=a['source_references']))
                sid=a['new_security_id']
        possible={old,sid}
        for t in sorted(self.doc.get('dated_identity_transitions',[]),key=lambda x:x['date']):
            if start<t['date']<=end and t['old_sid'] in possible:possible.add(t['new_sid'])
        if not possible & set(buy_sids):return dict(status='NOT_CURRENT_BUY')
        need(possible<={old,sid},'REFERENCE_UNREVIEWED_SUCCESSOR')
        all_sids={old,sid};gates=[]
        for checked_sid in sorted(all_sids):
            args=dict(decision_date=start,account_state=dict(shares={checked_sid:1}))
            selected=dict(target_quantities={checked_sid:1})
            if self.window=='2024_2026':
                from scripts.assemble_old_continuous_inputs_v1 import exposure_gate
                from scripts.run_old_continuous_probe_v4 import admit_reviewed_dividends,admit_period_absence
                gate=exposure_gate(self.doc,args,selected,end,end)
                gate=admit_reviewed_dividends(gate,self.review,self.doc['dividend_events'])
                gate=admit_period_absence(gate,self.review)
                if self.legacy_absence:gate=self.legacy_absence(gate)
            else:
                from scripts.run_recent_continuous_probe import exposed_action_blockers
                gate=exposed_action_blockers(args,selected,end,self.prices,self.review,active_date=end,dividend_events=self.doc['dividend_events'])
            remaining=[]
            for event in gate['unmapped_events']:
                c=next((v for v in conversions if v['date']==event.get('date')),None)
                accepted=False
                if event.get('kind')=='dividends':
                    matches=[r for r in self.cash_review['rows'] if r['status']=='REVIEWED_REFERENCE_ONLY_ORDINARY_CASH_DIVIDEND' and r['security_id']==checked_sid and r['ex_date']==event['date'] and event in r['observed_provider_events'] and r['reference_price_adjustment']=='NONE_NOMINAL_CLOSE_RULE' and r['cash_credit_authorized'] is False]
                    accepted=len(matches)==1
                if c and event.get('kind')=='splits':
                    p=event['provider_payload'];accepted=(event.get('ticker')=='SMCI' and F(p['numerator'])/F(p['denominator'])==10)
                elif c and event.get('kind')=='IDENTITY_CONVERSION':
                    accepted=(event.get('old_sid')==c['old_sid'] and event.get('new_sid')==c['new_sid'] and F(event['share_ratio'])==10 and event.get('coupled_distribution') is False)
                if not accepted:remaining.append(event)
            gate=dict(gate,unmapped_events=remaining,reference_conversions=deepcopy(conversions),scope_only_not_economic_holdings=True)
            self.audit.append(dict(interval_start=start,interval_end=end,gate=deepcopy(gate)))
            need(not remaining and not gate['missing_action_streams'],'REFERENCE_INTERVAL_ACTION_COVERAGE_BLOCKED:'+checked_sid+':'+start+':'+end)
            gates.append(gate)
        days=[d for d in self.domain['session_dates'] if start<d<=end]
        need(days and days[-1]==end,'REFERENCE_SESSION_COVERAGE')
        rows=[];sid=old
        for day in days:
            c=next((v for v in conversions if v['date']==day),None)
            if c:sid=c['new_sid']
            price=self.domain['close_prices'].get(sid,{}).get(day)
            need(price is not None and F(price)>0,'REFERENCE_NOMINAL_PRICE_MISSING:'+sid+':'+day)
            rows.append(dict(date=day,security_id=sid,close=price,conversion=c))
        proof=dict(status='VERIFIED',current_security_id=sid,completed_rows=rows,coverage=gates,price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED', source_hashes=self.domain['source_hashes'], split_timing_semantics='Original kernel events split_identity executes BEFORE_OPEN; omitted timing uses this existing event-type contract, explicit AFTER_CLOSE rejected')
        self.audit.append(dict(lock=deepcopy(lock),end=end,proof=proof));return proof
