import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('coverage_core', ROOT / 'backtest/ndx_saved_risk_classification_coverage_research.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def fixture():
    flags = {key: False for key in ('point_in_time_verified', 'legal_training_input_admitted', 'execution_authorized', 'fit_performed', 'promotion_allowed')}
    rows, gaps, selected = [], [], {}
    for i in range(101):
        ticker, sid = 'T'+str(i), 'security:'+str(i)
        issuer = 'issuer:'+str(0 if i == 1 else i)
        coordinate = dict(ticker=ticker, security_id=sid, issuer_id=issuer, cusip=str(i), security_class='common') if i < 78 else None
        label = 'hardware' if i < 78 else None
        row = dict(ticker=ticker, coordinate=coordinate, risk_chain=label, risk_sources=[{'original': i}], original_windows=[{'first': '2022-01-01'}], new_assumed_window={'first': '2026-03-20'}, gaps=['original'], **flags)
        if i == 0:
            row['bulk_extended_provenance_reference'] = {'json_pointer': '/bulk_extended_provenance/0'}
        rows.append(row)
        gaps.append(dict(ticker=ticker, included_in_conditional_panel=i < 77, blocking_reasons=[] if i < 77 else ['SAVED_VOLUME_BLOCK' if i == 77 else 'SAVED_NO_COORDINATE']))
        if i < 77:
            selected[sid] = dict(ticker=ticker, issuer_id=issuer, risk_chain=label)
    wiring = dict(schema='BULK_CONDITIONAL_IDENTITY_RISK_WIRING_V1', rows=rows, observed_member_count=101, candidate_security_count=78, candidate_issuer_count=77, calendar=['2026-03-20'], candidate_cutoff='2026-09-21', late_review_count=53, late_annual_tickers=['T0'], historical_denominators_preserved=[{'saved': i} for i in range(15)], bulk_extended_provenance=[{'review_selection_postdates_window_start': True, 'saved_review_date_fields': {'review': '2026-07-13'}, 'point_in_time_verified': False}], **flags)
    panel = dict(schema='DATED_CONDITIONAL_TRAINING_PANEL_V1', original_provenance_and_missing=gaps, fit_payload={'selected_by_security': selected}, security_count=77, issuer_count=76, observed_security_count=101, pool_scope='CONDITIONAL', original_identity_assumed_window={'first': '2026-03-20'}, evaluation_prior_fit_overlap_evidence={'prior_fit_task_count': 1632}, preserved_sidecar_references={'sidecar': {'saved': True}}, **flags)
    training = dict(schema='DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1', panel=panel, **flags)
    return dict(wiring=wiring, training_panel=training, wiring_reference=dict(path='wiring.json', sha256='a'*64, json_pointer=''), training_reference=dict(path='panel.json', sha256='b'*64, json_pointer=''))


class CoverageTests(unittest.TestCase):
    def test_denominators_and_exact_evidence_without_mutation(self):
        args = fixture()
        original = copy.deepcopy(args)
        out = core.summarize_saved_classification(**args)
        self.assertEqual(args, original)
        self.assertEqual((out['counts']['conditional_labeled_security_count'], out['counts']['unknown_label_rows'], out['counts']['training_selected_security_count']), (78, 23, 77))
        self.assertEqual(out['counts']['formally_verified_rows'], 0)
        self.assertEqual(out['rows'][77]['nonselection_evidence'], ['SAVED_VOLUME_BLOCK'])
        self.assertEqual(out['rows'][0]['original_wiring_row'], args['wiring']['rows'][0])
        self.assertEqual(out['rows'][0]['local_evidence']['bulk_extended_provenance_reference']['saved_evidence'], args['wiring']['bulk_extended_provenance'][0])
        self.assertEqual(len(out['saved_wiring_scope']['historical_denominators_preserved']), 15)

    def test_same_issuer_different_label_is_review_only(self):
        args = fixture()
        args['wiring']['rows'][1]['risk_chain'] = 'consumer'
        args['training_panel']['panel']['fit_payload']['selected_by_security']['security:1']['risk_chain'] = 'consumer'
        out = core.summarize_saved_classification(**args)
        self.assertEqual(out['issuer_label_reviews'][0]['status'], 'REVIEW_REQUIRED')
        self.assertIs(out['issuer_label_reviews'][0]['certified_classification_conflict'], False)
        self.assertNotEqual(out['rows'][0]['security_id'], out['rows'][1]['security_id'])

    def test_identity_and_inclusion_mismatch_rejected(self):
        for change in ('issuer', 'ticker', 'label', 'inclusion', 'extra'):
            args = fixture()
            selected = args['training_panel']['panel']['fit_payload']['selected_by_security']
            if change == 'inclusion':
                args['training_panel']['panel']['original_provenance_and_missing'][77]['included_in_conditional_panel'] = True
            elif change == 'extra':
                selected['unseen'] = selected['security:0'].copy()
            else:
                selected['security:0'][{'issuer': 'issuer_id', 'ticker': 'ticker', 'label': 'risk_chain'}[change]] = 'WRONG'
            with self.subTest(change=change), self.assertRaises(ValueError):
                core.summarize_saved_classification(**args)

    def test_authority_counts_and_unknown_never_upgraded(self):
        args = fixture()
        out = core.summarize_saved_classification(**args)
        self.assertIsNone(out['rows'][-1]['security_id'])
        self.assertEqual(out['rows'][-1]['classification_status'], 'UNKNOWN_SAVED_LABEL')
        for mutation in ('permission', 'boolcount', 'badref'):
            args = fixture()
            if mutation == 'permission':
                args['training_panel']['panel']['point_in_time_verified'] = 0
            elif mutation == 'boolcount':
                args['wiring']['candidate_security_count'] = True
            else:
                args['training_reference']['sha256'] = 'wrong'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                core.summarize_saved_classification(**args)


if __name__ == '__main__':
    unittest.main()
