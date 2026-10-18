from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_monthly_training import compile_saved_training,build_monthly_training_package
from data.current_quantity_v2_monthly_decision import QuantityV2MonthlyDecisionRegistry
from test_current_quantity_v2_monthly_decision import fixture as registry_fixture


def fixture(folder):
    registry,state,p=registry_fixture(folder);files=deepcopy(p['files']);days=[];day=date(2026,10,30)
    while len(days)<253:
        if day.weekday()<5:days.append(day.isoformat())
        day-=timedelta(days=1)
    days=sorted(days)
    def raw(ticker,dates):
        prices=list(range(100,100+len(dates)))
        return canonical({'chart':{'error':None,'result':[{'meta':dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),
            'timestamp':[int(datetime.fromisoformat(d+'T20:00:00+00:00').timestamp()) for d in dates],
            'indicators':{'quote':[{**{k:prices for k in ('open','high','low','close')},'volume':[10]*len(dates)}]}}]}})
    files['B.daily']=raw('BBB',days);files['C.daily']=raw('CCC',days[-20:]);files['A.held']=raw('AAA',[days[-1]])
    refs=['calendar-source'];rows=[]
    for ticker,sid,path,status in [('BBB','B','B.daily','READY_CONDITIONAL'),('CCC',None,'C.daily','EXCLUDED_TRAINING_RULE')]:
        rows.append(dict(ticker=ticker,security_id=sid,issuer_id='IB' if sid else None,status=status,identity_reviewed=bool(sid),coordinate_reviewed=True,
            identity_source_references=refs,coordinate_source_references=refs,training_source=path,raw_close=['999']*253,
            training_rule='RESTORED_PARENT_PRICE_ONLY',price_coordinate_factors=[dict(date=days[126],factor='3',source_references=refs)] if sid else [],
            true_share_events=[dict(date=days[126],ratio='2',source_references=refs)] if sid else [],decision_nominal_close='352' if sid else '119',blockers=[]))
    admission=dict(decision_date=days[-1],status='REVIEWED_CONDITIONAL',members=['BBB','CCC'],source_references=refs,
        training_exclusions={'CCC':dict(reason='INSUFFICIENT_253_SESSION_PREDECISION_HISTORY',known_asof=days[-1],source_references=['C.daily','calendar-source'])})
    calendar=json.loads(files['calendar.json']);calendar['training_dates']=days;files['calendar.json']=canonical(calendar)
    files['account_review.json']=canonical(dict(account_id=state['ledger']['account_id'],state_revision=state['ledger']['revision'],pending_rights=[],reviewed_at='2026-11-02T15:00:00+00:00',source_references=refs))
    pins={k:sha256(v).hexdigest() for k,v in files.items()}
    manifest=dict(decision_date=days[-1],coordinate_asof_date=days[-1],training_dates=days,members=['BBB','CCC'],candidates=rows,admission=admission,source_hashes=pins)
    files['manifest.json']=canonical(manifest);pins['manifest.json']=sha256(files['manifest.json']).hexdigest()
    return registry,state,dict(files=files,source_hashes=pins,documents={}),days


class CompilerTests(unittest.TestCase):
    def test_raw_253_compilation_exact_gross_and_no_search(self):
        with tempfile.TemporaryDirectory() as folder:
            _,_,package,days=fixture(folder);before=deepcopy(package)
            with patch('subprocess.run',side_effect=AssertionError('compiler must never search')):
                result=compile_saved_training(package,'manifest.json')
            args=result['input']['search_arguments'];self.assertEqual(set(args['prices']),{'B'})
            self.assertEqual(args['scenario_dates'],days[21::21]);self.assertEqual(len(args['training_scenarios']),12)
            training=[Fraction(100+i)*(Fraction(3,2) if i<126 else 1) for i in range(253)]
            self.assertEqual([Fraction(s['B']) for s in args['training_scenarios']],[training[i+21]/training[i] for i in range(0,252,21)])
            self.assertEqual(result['coverage'][1]['observed_training_sessions'],20);self.assertEqual(package,before)
            self.assertFalse(result['full_pit_verified'])

    def test_missing_middle_short_history_unreviewed_and_pin_drift(self):
        for mode in ('missing','shortgap','unreviewed','drift'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                _,_,p,_=fixture(folder)
                if mode=='drift':p['files']['B.daily']+=b' '
                else:
                    manifest=json.loads(p['files']['manifest.json'])
                    if mode=='unreviewed':manifest['admission']['training_exclusions']={}
                    else:
                        path='C.daily' if mode=='shortgap' else 'B.daily';raw=json.loads(p['files'][path]);raw['chart']['result'][0]['indicators']['quote'][0]['close'][10]=None
                        p['files'][path]=canonical(raw);p['source_hashes'][path]=sha256(p['files'][path]).hexdigest();manifest['source_hashes'][path]=p['source_hashes'][path]
                    p['files']['manifest.json']=canonical(manifest);p['source_hashes']['manifest.json']=sha256(p['files']['manifest.json']).hexdigest()
                with self.assertRaises(ValueError):compile_saved_training(p,'manifest.json')

    def test_full_account_wrapper_held_outside_only_valuation(self):
        with tempfile.TemporaryDirectory() as folder:
            registry,state,package,_=fixture(folder)
            with patch('subprocess.run',side_effect=AssertionError('compile must not search')):
                training=build_monthly_training_package(state,package,manifest_path='manifest.json',calendar_path='calendar.json',account_review_path='account_review.json',identities_path='identities.json',held_bar_sources={'A':'A.held'},now='2026-11-02T15:00:00+00:00')
            data=json.loads(training['files'][training['documents']['training']])
            self.assertEqual(set(data['search_arguments']['prices']),{'B'});self.assertEqual(set(data['bar_sources']),{'A','B'})
            self.assertEqual({q['security_id'] for q in data['valuation_quotes']},{'A','B'})
            # Registry preflight reads bytes/account/calendar but does not execute a worker.
            _,arguments,_,_,_=registry._prepare(state,training)
            self.assertEqual(arguments['account_state']['shares'],state['ledger']['shares'])
            self.assertFalse(registry.root.exists())

if __name__=='__main__':unittest.main()
