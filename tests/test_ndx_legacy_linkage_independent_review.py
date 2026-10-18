"""Synthetic final-step attacks, with hashes rebuilt to test semantic guards."""
import hashlib
import unittest
import test_ndx_legacy_target_distance_schedule_linkage_recovery_20260923 as fixtures

m=fixtures.m


def replace(ref,doc):
    from pathlib import Path
    path=Path(ref['path']);path.write_bytes(m.encoded(doc))
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def alter_last(audit,operation):
    detail=audit['details'][-1]
    started=m.read(detail['started_reference'],{});raw=m.read(detail['raw_reference'],{});final=m.read(detail['finalization_reference'],{})
    operation(started,raw,final,detail)
    detail['started_reference']=replace(detail['started_reference'],started);raw['started_reference']=detail['started_reference']
    detail['raw_reference']=replace(detail['raw_reference'],raw);final['raw_reference']=detail['raw_reference']
    detail['finalization_reference']=replace(detail['finalization_reference'],final)
    audit['finalization_references'][-1]=detail['finalization_reference']


class IndependentReview(unittest.TestCase):
    def test_started_cannot_claim_actual_call_even_with_new_hash(self):
        with fixtures.fixture() as (folder,audit):
            alter_last(audit,lambda start,raw,final,detail:start.update(wrapper_call_attempt_count=1))
            ref=m.publish(folder/'audit.json',audit)
            with self.assertRaisesRegex(ValueError,'planned versus actual'):m.reconstruct(ref)

    def test_equal_raw_or_final_numeric_request_not_allowed(self):
        for target in ('raw','final'):
            with fixtures.fixture() as (folder,audit):
                def attack(start,raw,final,detail):
                    (raw if target=='raw' else final)['numerical_fit_request_count']=1
                alter_last(audit,attack);ref=m.publish(folder/'audit.json',audit)
                with self.subTest(target=target),self.assertRaisesRegex(ValueError,'Actual wrapper'):m.reconstruct(ref)

    def test_full_prior_and_exit_risk_union_not_dropped(self):
        for attack in ('prior','union'):
            with fixtures.fixture() as (folder,audit):
                def mutate(start,raw,final,detail):
                    if attack=='prior':raw['fitted']['previous_target_weights'].pop('S0')
                    else:
                        for item in (start,raw,detail):item['numerical_and_lane_binding']['lane_risk_chains_by_security'].pop('S0',None)
                        detail['lane_risk_chains_by_security'].pop('S0',None)
                alter_last(audit,mutate);ref=m.publish(folder/'audit.json',audit)
                with self.subTest(attack=attack),self.assertRaises(ValueError):m.reconstruct(ref)
                self.assertFalse((folder/'schedule.json').exists())

    def test_false_finalization_scope_and_missing_independent_diff_source(self):
        for attack in ('promotion','diff_source'):
            with fixtures.fixture() as (folder,audit):
                if attack=='promotion':alter_last(audit,lambda start,raw,final,detail:final.update(promotion_allowed=True))
                else:
                    path=audit['details'][-1]['numerical_and_lane_binding']['candidate_provenance']['independent_full_diff_reference']['path']
                    del audit['source_hashes'][path]
                ref=m.publish(folder/'audit.json',audit)
                with self.subTest(attack=attack),self.assertRaises(ValueError):m.reconstruct(ref)


if __name__=='__main__':unittest.main()
