from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_taxonomy_review import (
    build_filing_plan_gaps,
    extract_business_section,
)


class NdxTaxonomyReviewTests(unittest.TestCase):
    def test_extracts_ixbrl_split_heading_words(self):
        body = " ".join([
            "Overview We provide regional freight transportation services to customers",
            "through an integrated service-center network with technology-supported operations.",
        ] * 20)
        html = f"""
        <html><body>
        <div>Table of Contents Item 1 Business Item 1A Risk Factors</div>
        <h1>PART I ITEM 1. B USINESS</h1><p>{body}</p>
        <h1>ITEM 1A. RI SK FACTORS</h1><p>Risk text.</p>
        </body></html>
        """
        result = extract_business_section(html, "10-K")
        self.assertEqual(result["extraction_status"], "business_section_extracted")
        self.assertIn("regional freight transportation", result["section_text"])

    def test_extracts_explicit_registrant_name_20f_item4_heading(self):
        body = " ".join([
            "Check Point develops and supports information-security products for enterprise customers",
            "through a portfolio of network, cloud, endpoint, and mobile security solutions.",
        ] * 20)
        html = f"""
        <html><body>
        <div>Table of Contents Item 4. Information on Check Point Item 4A. Unresolved Staff Comments</div>
        <p>For additional information, see Item 4 - Information on Check Point.</p>
        <div>18 Table of Contents</div>
        <h1>ITEM 4. INFORMATION ON CHECK POINT</h1><p>{body}</p>
        <h1>ITEM 4A. UNRESOLVED STAFF COMMENTS</h1><p>None.</p>
        </body></html>
        """
        result = extract_business_section(html, "20-F")
        self.assertEqual(result["extraction_status"], "business_section_extracted")
        self.assertIn("information-security products", result["section_text"])

    def test_extracts_long_business_section_not_table_of_contents(self):
        html = """
        <html><head><title>Example 10-K</title></head><body>
        <div>Table of Contents Item 1. Business Item 1A. Risk Factors</div>
        <div>ITEM 1. BUSINESS. The company operates a semiconductor design and
        manufacturing business with multiple product lines and customers. This
        paragraph is intentionally repeated to make the section substantive.
        The company manages research, engineering, sales, manufacturing and
        support operations across several regions. The business description
        continues with products, markets, customers, competition and employees.
        The company also describes its product development process, supply
        chain, distribution channels, intellectual property, seasonality and
        regulatory environment. These facts are included for manual review and
        are not a risk-chain decision by this extractor.
        </div>
        <div>ITEM 1A. RISK FACTORS. Risks follow.</div>
        </body></html>
        """
        result = extract_business_section(html, "10-K")
        self.assertEqual(result["extraction_status"], "business_section_extracted")
        self.assertIn("semiconductor design", result["section_text"])
        self.assertNotIn("Table of Contents", result["section_text"])

    def test_quarterly_filing_without_standardized_business_section_stays_pending(self):
        result = extract_business_section(b"<html><body>Item 1. Financial Statements</body></html>", "10-Q")
        self.assertEqual(result["extraction_status"], "no_standardized_business_section")
        self.assertEqual(result["section_text"], "")

    def test_20f_prefers_primary_item_four_over_cross_reference(self):
        html = """
        <html><body>
        Item 4. Information on the Company—B. Business Overview—Regulation—
        a cross-reference that must not be selected.
        Item 4. Information on the Company A. History and Development of the Company
        Corporate history.
        B. Business Overview We operate a technology-driven e-commerce marketplace
        for buyers, merchants and logistics partners. The business description
        covers products, customers, operations, technology, competition, supply
        chain, employees and regulation in sufficient detail for review. We also
        describe the marketplace model, merchant onboarding, customer service,
        fulfillment network, warehouse operations, delivery partners, software,
        data governance, research and development, sales channels, pricing,
        intellectual property, seasonality, employees, regional operations,
        regulatory requirements and the risks relevant to the business model.
        Item 5. Operating and Financial Review and Prospects.
        """
        result = extract_business_section(html, "20-F")
        self.assertEqual(result["extraction_status"], "business_section_extracted")
        self.assertIn("technology-driven e-commerce marketplace", result["section_text"])
        self.assertNotIn("cross-reference that must not be selected", result["section_text"])

    def test_20f_rejects_early_history_cross_reference_to_financial_tables(self):
        html = """
        <html><body>
        Item 4. Information on the Company A. History and Development of the Company
        for further information. The selected consolidated statements of operations
        and balance sheet data were derived from audited financial statements. This
        financial cross-reference includes enough filler words to exceed the minimum
        section length but does not describe products, customers, or operations.
        Additional financial data and historical results continue in this reference.
        Item 5. Operating and Financial Review and Prospects.
        Item 4. Information on the Company A. History and Development of the Company
        Corporate history and organization details.
        B. Business Overview We are a technology-driven e-commerce company providing
        retail, marketplace, logistics and supply-chain services to customers and
        merchants. We operate fulfillment infrastructure, software platforms,
        warehouses, delivery networks and customer-service operations. Our business
        description also covers products, suppliers, competition, employees,
        research and development, sales channels, intellectual property, regulation,
        regional operations, pricing and data governance for manual review.
        Item 5. Operating and Financial Review and Prospects.
        </body></html>
        """

        result = extract_business_section(html, "20-F")

        self.assertEqual(result["extraction_status"], "business_section_extracted")
        self.assertIn("technology-driven e-commerce company", result["section_text"])
        self.assertNotIn("selected consolidated statements", result["section_text"])

    def test_missing_filing_plan_is_fail_closed(self):
        plan = pd.DataFrame([
            {
                "job_id": "job-a",
                "security_id": "security:0000000001:A",
                "issuer_id": "issuer:0000000001",
                "ticker": "AAA",
                "cik": "0000000001",
                "cusip": "A",
                "observation_from": "2020-01-01",
                "evidence_required_from": "2020-01-01",
                "plan_status": "needs_sec_filing_plan",
            },
            {
                "job_id": "job-b",
                "security_id": "security:0000000002:B",
                "issuer_id": "issuer:0000000002",
                "ticker": "BBB",
                "cik": "0000000002",
                "cusip": "B",
                "observation_from": "2020-01-01",
                "evidence_required_from": "2020-01-01",
                "plan_status": "identity_unresolved",
            },
        ])
        attempts = pd.DataFrame([{
            "job_id": "job-a",
            "status": "failed",
        }])
        gaps = build_filing_plan_gaps(plan, attempts)
        self.assertEqual(set(gaps["issue_type"]), {"missing_sec_filing_plan", "identity_unresolved"})
        self.assertTrue(gaps["classification_allowed"].eq(False).all())
        self.assertTrue(gaps["future_data_guard"].eq("evidence_available_date <= selection_date").all())


if __name__ == "__main__":
    unittest.main()
