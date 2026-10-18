"""One real prepare/validate baseline, then explicit cached semantic isolation.

Cached negatives do not certify a separately authenticated modified source pack.
No existing producer/parser/apply/economic module is executed.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_business_review_prepare_adapter_research_v1 as module


class IndependentPrepareReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        instances=[];parsers={}
        constructor=module._FixedSources
        parser_constructor=module._OriginalHTML
        def sources():
            instance=constructor();instances.append(instance);return instance
        def parser(raw):
            value=parser_constructor(raw);parsers[module._sha(raw)]=value;return value
        with patch.object(module,'_FixedSources',side_effect=sources),patch.object(module,'_OriginalHTML',side_effect=parser):
            cls.pack=module.prepare_reviewpack()
            cls.validated=module.validate_reviewpack(cls.pack)
        cls.inputs=instances[0];cls.parsers=parsers
        cls.real_fixed_roster_loads=len(instances)
        assert cls.real_fixed_roster_loads==2

    def test_real_complete_template_and_detached_output(self):
        self.assertEqual(self.pack,self.validated)
        self.assertEqual(len(self.pack['source_hashes']),271)
        self.assertEqual(sum(r['complete_business_evidence'] is not None for r in self.pack['rows']),9)
        self.assertEqual(self.pack['independently_reconstructed_counts'],{'direct_section_children':960,'ccep_page_occurrences':43,'fer_content_children':1155})
        self.assertEqual(len(self.pack['rows'][-1]['original_identity_candidates']),2)
        self.validated['rows'][0]['original_identity_candidates'][0]['row']['security_id']='caller mutation'
        self.assertNotEqual(self.pack,self.validated)
        self.assertNotEqual(self.inputs.document(module.PLAN)['rows'][0]['original_identity_candidates'][0]['row']['security_id'],'caller mutation')

    def test_unknown_shape_and_source_claims_cannot_read_trap(self):
        trap=str(module.ROOT/'tmp/NO_READ_BUSINESS_TRAP.html')
        reference={'path':trap,'sha256':'a'*64}
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Any follow IO forbidden')) as reads:
            for value in (reference,dict(reference,approved=True),dict(reference,path=str(module.ROOT/module.PLAN),sha256='0'*64)):
                with self.assertRaises(ValueError):self.inputs.follow(value)
            with patch.object(module,'prepare_reviewpack',return_value=deepcopy(self.pack)):
                for shape in ('source_only','shape_and_source'):
                    bad=deepcopy(self.pack);bad['source_hashes'][trap]='a'*64
                    if shape=='shape_and_source':bad['rows'][0]['extra_evidence_reference']=reference
                    with self.assertRaises(ValueError):module.validate_reviewpack(bad)
            self.assertEqual(reads.call_count,0)

    def test_cached_validator_privilege_identity_quote_and_legacy_cast(self):
        changes=[
            lambda p:p['rows'][-1]['original_identity_candidates'].pop(),
            lambda p:p['rows'][-1]['template'].update(security_id=p['rows'][-1]['original_identity_candidates'][0]['row']['security_id']),
            lambda p:p['rows'][-2].update(complete_business_evidence=deepcopy(p['rows'][0]['complete_business_evidence'])),
            lambda p:p['rows'][0]['template'].update(status='accepted',risk_chain='ai_accelerator',confidence='high'),
            lambda p:p['rows'][0].update(source_available_at_utc=p['rows'][0]['local_fetched_at_as_declared']),
            lambda p:p['rows'][0]['template'].update(evidence_available_date=p['rows'][0]['original_source_available_date_as_declared']),
            lambda p:p['rows'][0]['complete_business_evidence'].update(schema='business_section_extracted'),
            lambda p:p['rows'][0]['complete_business_evidence'].update(saved_text_codepoint_start=p['rows'][0]['complete_business_evidence']['saved_text_codepoint_start']+1),
            lambda p:p['rows'][0]['complete_business_evidence']['complete_original_nodes'].reverse(),
        ]
        # Use a multi-node quote for the order mutation; AMD's single node reversal
        # is intentionally not treated as a changed input.
        changes[-1]=lambda p:p['rows'][-1]['complete_business_evidence']['complete_original_nodes'].reverse()
        for flag in module.FALSE_FIELDS:
            for replacement in (0,None,True,'false'):
                changes.append(lambda p,k=flag,v=replacement:p['rows'][0].update({k:v}))
        with patch.object(module,'prepare_reviewpack',return_value=deepcopy(self.pack)):
            for index,change in enumerate(changes):
                bad=deepcopy(self.pack);change(bad)
                with self.subTest(index=index),self.assertRaises(ValueError):module.validate_reviewpack(bad)
        self.assertEqual(len(changes),61)

    def cached_rebuild(self, relative, change):
        inputs=object.__new__(module._FixedSources)
        inputs.__dict__=deepcopy(self.inputs.__dict__)
        document=module._json(inputs.raw[relative]);change(document)
        inputs.raw[relative]=module._encoded(document)
        # This deliberately bypasses source SHA/resource/final IO gates to isolate
        # derived semantic checks on previously authenticated in-memory originals.
        inputs.final_guard=lambda:None
        with patch.object(module,'_FixedSources',return_value=inputs),patch.object(module,'_OriginalHTML',side_effect=lambda raw:self.parsers[module._sha(raw)]),patch.object(Path,'read_bytes',side_effect=AssertionError('Cached semantic test must not read')):
            return module.prepare_reviewpack()

    def test_cached_derived_semantic_truncation_offset_and_fer_order(self):
        plan=self.inputs.document(module.PLAN)
        fer=plan['rows'][-1]['full_business_fact_reference']
        fer_relative=self.inputs.paths[module.os.path.normcase(module.os.path.abspath(fer['path']))]
        changes=[
            (module.PLAN,lambda d:d['rows'][0]['business_evidence'].update(saved_text_codepoint_stop=d['rows'][0]['business_evidence']['saved_text_codepoint_stop']-1)),
            (module.PLAN,lambda d:d['rows'][0]['business_evidence'].update(full_text_codepoint_start=True)),
            (module.PLAN,lambda d:d['rows'][-1]['original_identity_candidates'].pop()),
            (fer_relative,lambda d:d['segments'].reverse()),
            (fer_relative,lambda d:d['segments'].pop()),
            ('tmp/ccep_item4_complete_referenced_pages_20261009_v1/B/section.json',lambda d:d['page_occurrences'].reverse()),
            ('tmp/four_business_sections_and_fer_exclusion_20261009_v1/FER.header_footer_exclusion_plan.json',lambda d:d['excluded_page_wrappers'].pop()),
        ]
        for relative,change in changes:
            with self.subTest(relative=relative),self.assertRaises(ValueError):self.cached_rebuild(relative,change)

    def test_final_guard_late_raw_and_namespace_drift(self):
        original_read=Path.read_bytes
        target=module.ROOT/'tmp/fer_item4b_complete_segments_20261009_v1/segment_27.txt'
        def late_read(path):return original_read(path)+b'late drift' if path==target else original_read(path)
        with patch.object(Path,'read_bytes',late_read),self.assertRaisesRegex(ValueError,'Final fixed source drift'):
            self.inputs.final_guard()
        original_inventory=module._inventory
        target_namespace=module.ROOT/'tmp/conditional_business_dom_ranges_20261009_v1'
        def late_inventory(folder):
            names=original_inventory(folder)
            return names+['unapproved_extra_fact.json'] if folder==target_namespace else names
        with patch.object(module,'_inventory',side_effect=late_inventory),self.assertRaisesRegex(ValueError,'inventory drift'):
            self.inputs.final_guard()


if __name__=='__main__':unittest.main()
