from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_filing_identity import (
    FilingShareResolutionPolicy,
    NdxFilingIdentityError,
    build_filing_identity_plan,
    parse_filing_share_facts,
    resolve_filing_share_rows,
    select_xbrl_instance,
)


class NdxFilingIdentityTests(unittest.TestCase):
    def test_index_selection_requires_an_explicit_instance(self):
        selected = select_xbrl_instance({
            "directory": {
                "item": [
                    {"name": "FilingSummary.xml"},
                    {"name": "meta-20221231_htm.xml", "size": 123},
                ]
            }
        })
        self.assertEqual(selected["name"], "meta-20221231_htm.xml")
        self.assertEqual(
            selected["selection_method"],
            "explicit_inline_xbrl_instance",
        )
        with self.assertRaisesRegex(NdxFilingIdentityError, "ambiguous or missing"):
            select_xbrl_instance({
                "directory": {"item": [{"name": "primary.htm"}]}
            })

    def test_dimensional_share_facts_are_preserved_not_summed(self):
        xml = b"""<?xml version='1.0'?>
<xbrl xmlns='http://www.xbrl.org/2003/instance'
 xmlns:xbrli='http://www.xbrl.org/2003/instance'
 xmlns:xbrldi='http://xbrl.org/2006/xbrldi'
 xmlns:dei='http://xbrl.sec.gov/dei/2024'
 xmlns:us-gaap='http://fasb.org/us-gaap/2024'>
  <xbrli:context id='ClassA'>
    <xbrli:entity><xbrli:identifier scheme='http://www.sec.gov/CIK'>0001326801</xbrli:identifier>
      <xbrli:segment><xbrldi:explicitMember dimension='us-gaap:StatementClassOfStockAxis'>meta:ClassACommonStockMember</xbrldi:explicitMember></xbrli:segment>
    </xbrli:entity><xbrli:period><xbrli:instant>2024-01-26</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id='ClassB'>
    <xbrli:entity><xbrli:identifier scheme='http://www.sec.gov/CIK'>0001326801</xbrli:identifier>
      <xbrli:segment><xbrldi:explicitMember dimension='us-gaap:StatementClassOfStockAxis'>meta:ClassBCommonStockMember</xbrldi:explicitMember></xbrli:segment>
    </xbrli:entity><xbrli:period><xbrli:instant>2024-01-26</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:unit id='shares'><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
  <dei:EntityCommonStockSharesOutstanding contextRef='ClassA' unitRef='shares' decimals='INF'>2100000000</dei:EntityCommonStockSharesOutstanding>
  <dei:EntityCommonStockSharesOutstanding contextRef='ClassB' unitRef='shares' decimals='INF'>350000000</dei:EntityCommonStockSharesOutstanding>
</xbrl>"""
        facts = parse_filing_share_facts(
            xml,
            cik=1326801,
            accession_number="0001326801-24-000012",
            source_url="https://www.sec.gov/example.xml",
        )
        self.assertEqual(len(facts), 2)
        self.assertEqual(list(facts["value"]), [2100000000.0, 350000000.0])
        self.assertTrue(facts["entity_identifier_matches_cik"].all())
        self.assertTrue((facts["dimensions_count"] == 1).all())

    def test_plan_only_targets_identity_blockers_and_exact_filing(self):
        readiness = pd.DataFrame([
            {
                "selection_date": "2024-02-01",
                "ticker": "META",
                "cik": 1326801,
                "shares_ready": False,
                "multi_security_issuer": False,
                "foreign_filer_asof": False,
            },
            {
                "selection_date": "2024-02-01",
                "ticker": "AAPL",
                "cik": 320193,
                "shares_ready": True,
                "multi_security_issuer": False,
                "foreign_filer_asof": False,
            },
        ])
        sic = pd.DataFrame([
            {
                "selection_date": "2024-02-01",
                "ticker": "META",
                "cik": 1326801,
                "accession_number": "0001326801-24-000012",
                "form": "10-K",
                "filed_date": "2024-01-26",
                "available_date": "2024-01-27",
                "sic_future_data_guard_passed": True,
            },
            {
                "selection_date": "2024-02-01",
                "ticker": "AAPL",
                "cik": 320193,
                "accession_number": "0000320193-24-000006",
                "form": "10-Q",
                "filed_date": "2024-01-26",
                "available_date": "2024-01-27",
                "sic_future_data_guard_passed": True,
            },
        ])
        jobs, mapped = build_filing_identity_plan(readiness, sic)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(mapped), 1)
        self.assertEqual(jobs.iloc[0]["tickers"], "META")
        self.assertEqual(mapped.iloc[0]["identity_reason"], "shares_not_ready")

    def test_share_resolution_sums_explicit_common_classes_but_keeps_gates(self):
        facts = pd.DataFrame([
            {
                "cik": 1326801,
                "accession_number": "0001326801-24-000012",
                "concept": "EntityCommonStockSharesOutstanding",
                "period_end": "2024-01-26",
                "unit_measure": "shares",
                "value": value,
                "entity_identifier_matches_cik": True,
                "dimensions_count": 1,
                "dimensions_json": (
                    '[{"axis":"us-gaap:StatementClassOfStockAxis",'
                    f'"member":"us-gaap:{member}"}}]'
                ),
                "source_url": "https://www.sec.gov/example.xml",
            }
            for member, value in [
                ("CommonClassAMember", 2100000000),
                ("CommonClassBMember", 350000000),
            ]
        ])
        jobs = pd.DataFrame([{
            "cik": 1326801,
            "accession_number": "0001326801-24-000012",
            "available_date": "2024-01-27",
            "form": "10-K",
        }])
        identity = pd.DataFrame([{
            "selection_date": "2024-02-01",
            "ticker": "META",
            "cik": 1326801,
        }])
        readiness = pd.DataFrame([{
            "selection_date": "2024-02-01",
            "ticker": "META",
            "cik": 1326801,
            "shares_ready": False,
            "shares_value": None,
            "foreign_filer_asof": False,
            "multi_security_issuer": False,
        }])
        rows, comparisons, promotions, failures = resolve_filing_share_rows(
            identity,
            facts,
            jobs,
            readiness,
            policy=FilingShareResolutionPolicy(
                maximum_domestic_share_age_days=200,
            ),
        )
        self.assertEqual(rows.iloc[0]["resolved_shares_value"], 2450000000.0)
        self.assertEqual(
            rows.iloc[0]["share_resolution_method"],
            "explicit_common_class_sum",
        )
        self.assertTrue(bool(rows.iloc[0]["promotion_allowed"]))
        self.assertEqual(len(promotions), 1)
        self.assertTrue(comparisons.empty)
        self.assertTrue(failures.empty)


if __name__ == "__main__":
    unittest.main()
