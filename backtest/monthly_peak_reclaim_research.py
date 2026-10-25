"""Research-only exit20 with re-entry only on reclaiming the prior monthly peak."""
from fractions import Fraction as F

class MonthlyPeakReclaim:
 def __init__(self):
  self.month=None;self.peaks={};self.exited=set()
 def apply(self,*,day,month,target,closes,adjustments=()):
  if adjustments:raise ValueError('SPLIT_ADAPTER_REQUIRED')
  if month!=self.month:
   if day!=month:raise ValueError('MONTH_MUST_START_AT_DECISION_CLOSE')
   self.month=month;self.peaks={};self.exited=set()
  effective=dict(target);diagnostics={}
  for sid,quantity in target.items():
   if not quantity:continue
   close=F(closes[sid])
   if close<=0:raise ValueError('POSITIVE_CLOSE_REQUIRED')
   prior_peak=self.peaks.get(sid,close)
   reclaimed=sid in self.exited and close>=prior_peak
   if reclaimed:self.exited.remove(sid)
   peak=max(prior_peak,close);self.peaks[sid]=peak
   triggered=close<=peak*F(4,5)
   if triggered:self.exited.add(sid)
   if sid in self.exited:effective[sid]=0
   diagnostics[sid]=dict(close=str(close),monthly_peak=str(peak),triggered=triggered,latched=sid in self.exited,reclaimed=reclaimed,target_before=quantity,target_after=effective[sid])
  return effective,diagnostics
