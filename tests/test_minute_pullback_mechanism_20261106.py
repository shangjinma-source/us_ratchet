from copy import deepcopy
from scripts.research import ibm_minute_pullback_mechanism_20261106 as m

def test_later_missing_bar_cannot_remove_existing_trigger():
 _,minutes=m.load();bars=minutes['2026-10-28'];signal,_=m.trigger(bars)
 assert signal and signal['entry_t']==580
 shortened=bars[:signal['entry_index']+1]
 assert m.trigger(shortened)[0]==signal
 changed=deepcopy(bars);changed[-1]['c']*=10
 assert m.trigger(changed)[0]==signal

def test_future_daily_close_cannot_modify_prior_filter():
 daily,_=m.load();base=m.filters(daily);changed=deepcopy(daily);changed[-1]['c']*=10
 result=m.filters(changed)
 assert all(base[k]==result[k] for k in base if k<daily[-1]['date'])

def test_next_open_requires_setup_survival_and_preserves_unknown():
 _,minutes=m.load();dates=sorted(minutes)
 for day,expected in [('2026-10-26','SETUP_INVALIDATED_BEFORE_NEXT_OPEN'),('2026-10-29','UNKNOWN_SETUP_SURVIVAL_GAP')]:
  signal,_=m.trigger(minutes[day]);event=dict(date=day,**signal)
  assert m.trade(minutes,dates,event,'NEXT_OPEN')['status']==expected
