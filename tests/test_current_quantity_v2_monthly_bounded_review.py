"""Synthetic raw evidence tests; no network or economic historical run."""
import base64
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data.current_quantity_v2_monthly_bounded_review import MonthlyBoundedUnitReview,replay_monthly_review
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_monthly_factory import attach_monthly_services
from test_current_quantity_v2_monthly_research_service import fixture
from test_current_quantity_v2_bounded_unit_review import feed


def setup(folder):
    research,state,_,old,paper,clock=fixture(folder)
    selected=research.generate(account_id=state['ledger']['account_id'],expected_revision=state['ledger']['revision'])
    seen=[];calls=[]
    def account(s):
        seen.append(deepcopy(s));p=old.review_reader(s)
        return dict(files=p['files'],source_hashes=p['source_hashes'],account_review_path=p['documents']['account_review'])
    reader=MonthlyBoundedUnitReview(account_review_reader=account,fetch=lambda:(calls.append(1) or dict(status=200,body=feed())),clock=lambda:clock[0])
    paper.clock=lambda:clock[0]
    parts=attach_monthly_services(paper,storage_root=Path(folder)/'capture',decision_reader=research.decision_reader,review_reader=reader,fetch=old.fetch)
    proposal=paper.monthly_preview(account_id=state['ledger']['account_id'],decision_id=selected['decision_id'],expected_revision=state['ledger']['revision'])
    snapshot=seen[0];result=reader.read(snapshot)
    return snapshot,result,reader,clock,calls,proposal


def unit(result,kind='unit_continuity'):
    return next(iter(json.loads(result['files'][result['documents'][kind]]).values()))


def replay(s,r,u,held=False):
    sid=u['security_id'];pins={**s['base_source_hashes'],**r['source_hashes']}
    pins.update({p:sha256(v).hexdigest() for p,v in s['quote_files'].items()})
    return replay_monthly_review(u,security=s['identities']['securities'][sid],current=s['current_receipts'][sid],source_hashes=pins,
        now=u['reviewed_at'],capital_decision=None if held else s['capital_decision'],origin=u['bounded_evidence'].get('origin'),held_capital_decision=s['capital_decision'] if held else None)


class MonthlyBoundedTests(unittest.TestCase):
    def test_read_no_fetch_and_stale_and_snapshot_change(self):
        with TemporaryDirectory() as folder:
            s,r,reader,clock,calls,p=setup(folder)
            self.assertEqual(calls,[1]);self.assertFalse(p['unit_review']['coverage_complete'])
            reader.read(s);self.assertEqual(calls,[1])
            changed=deepcopy(s);changed['capital_decision']['decision_id']='f'*64
            with self.assertRaises(ValueError):reader.read(changed)
            clock[0]+=timedelta(seconds=121)
            with self.assertRaises(ValueError):reader.read(s)
            self.assertEqual(calls,[1])

    def test_outer_pin_and_contradictory_fields_rejected(self):
        with TemporaryDirectory() as folder:
            s,r,reader,clock,calls,p=setup(folder);u=unit(r)
            for key,value in [('ticker','WRONG'),('price_basis','ADJUSTED'),('covered_from_date','2000-01-01'),('known_actions',['split'])]:
                bad=deepcopy(u);bad[key]=value
                with self.assertRaises(ValueError):replay(s,r,bad)
            bad=deepcopy(u);e=bad['bounded_evidence'];path=e['rss_raw_path']
            raw=base64.b64decode(e['files'][path])+b' '
            e['files'][path]=base64.b64encode(raw).decode();e['source_hashes'][path]=sha256(raw).hexdigest()
            with self.assertRaises(ValueError):replay(s,r,bad)

    def test_daily_granularity_and_oldheld_gap_events(self):
        with TemporaryDirectory() as folder:
            s,r,reader,clock,calls,p=setup(folder)
            for held in (False,True):
                u=unit(r,'held_unit_continuity' if held else 'unit_continuity');e=u['bounded_evidence'];path=e['daily_raw_path']
                original=json.loads(base64.b64decode(e['files'][path]))
                changed=deepcopy(original);changed['chart']['result'][0]['meta']['dataGranularity']='1m'
                raw=canonical(changed);e['files'][path]=base64.b64encode(raw).decode();e['source_hashes'][path]=sha256(raw).hexdigest()
                rr=deepcopy(r);rr['source_hashes'][path]=sha256(raw).hexdigest()
                with self.assertRaises(ValueError):replay(s,rr,u,held)
            u=unit(r,'held_unit_continuity');e=u['bounded_evidence'];path=e['daily_raw_path']
            raw=json.loads(base64.b64decode(e['files'][path]));chart=raw['chart']['result'][0]
            from data.current_quantity_v2_difference_plan import stamp
            event_at=int((stamp(e['origin']['captured_at'])+timedelta(seconds=1)).timestamp())
            chart['events']={'splits':{str(event_at):{'date':event_at,'numerator':2,'denominator':1}}}
            encoded=canonical(raw);e['files'][path]=base64.b64encode(encoded).decode();e['source_hashes'][path]=sha256(encoded).hexdigest()
            rr=deepcopy(r);rr['source_hashes'][path]=sha256(encoded).hexdigest()
            with self.assertRaisesRegex(ValueError,'BOUNDED_UNIT_CHANGE_CANDIDATE'):replay(s,rr,u,True)
            rogue=deepcopy(u);ev=rogue['bounded_evidence'];ev['daily_raw_path']='other/daily.json'
            ev['files']['other/daily.json']=ev['files'][path];ev['source_hashes']['other/daily.json']=ev['source_hashes'][path]
            rr['source_hashes']['other/daily.json']=ev['source_hashes'][path]
            with self.assertRaisesRegex(ValueError,'MONTHLY_BOUNDED_REVIEW_UNAVAILABLE'):replay(s,rr,rogue,True)


if __name__=='__main__':unittest.main()
