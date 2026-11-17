"""Unit tests for bank import posting-plan errors and import summary.

DB-backed helpers are mocked, following the pattern of ``lithuania_compliance.api.test_isaf``.
"""

import unittest
from unittest.mock import patch

import frappe

from lithuania_compliance.lithuania_compliance.doctype.bank_importer import bank_importer


def outgoing_transaction(**kwargs):
	values = {
		"date": "2026-11-08",
		"direction": "DBIT",
		"amount": 12.34,
		"currency": "EUR",
		"reference_no": "2026110802819074-1",
		"remittance_reference": "Mokejimas uz prekes",
		"structured_reference": None,
		"party_name": "UAB NEZINOMAS TIEKEJAS",
		"party_iban": "LT367300000123456789",
		"party_address": "",
		"subfamily_code": "ICDT",
	}
	values.update(kwargs)
	return bank_importer.CamtTransaction(**values)


class TestBuildPostingPlan(unittest.TestCase):
	def setUp(self):
		self.context = bank_importer.AccountContext(
			account="Bank - T", company="Test Company", bank_account="Bank Account - T"
		)
		self.settings = frappe._dict(
			{
				"structured_reference_account_mapping": [],
				"bank_fee_expense_account": None,
				"bank_fee_cost_center": None,
			}
		)

	def build(self, txn, matches):
		return bank_importer.build_posting_plan(txn, matches, None, None, self.context, self.settings)

	@patch.object(bank_importer, "fmt_money", side_effect=lambda amount, currency=None: f"{amount:.2f}")
	def test_unresolved_outgoing_party_raises_posting_plan_error(self, _fmt_money):
		with self.assertRaises(bank_importer.PostingPlanError) as raised:
			self.build(outgoing_transaction(), bank_importer.MatchResult())

		message = str(raised.exception)
		self.assertIn("2026110802819074-1", message)
		self.assertIn("UAB NEZINOMAS TIEKEJAS", message)
		self.assertIn("LT367300000123456789", message)
		self.assertIn("12.34", message)

	def test_matched_supplier_still_builds_pay_plan(self):
		plan = self.build(
			outgoing_transaction(), bank_importer.MatchResult(party_type="Supplier", party="S-1")
		)

		self.assertEqual(plan.payment_type, "Pay")
		self.assertEqual(plan.party_type, "Supplier")
		self.assertEqual(plan.party, "S-1")
		bank_importer.validate_posting_plan(plan)

	def test_incomplete_plan_raises_posting_plan_error(self):
		plan = bank_importer.PostingPlan("Pay", paid_from=None, party_type="Supplier", party="S-1")

		with self.assertRaises(bank_importer.PostingPlanError):
			bank_importer.validate_posting_plan(plan)


class TestBuildImportSummary(unittest.TestCase):
	@patch.object(bank_importer, "create_reconciliation_documents", return_value=[])
	def test_reports_created_documents_and_unreconciled_separately(self, _reconciliations):
		results = [
			bank_importer.ImportResult("PE-1", "Payment Entry", True, "Supplier", "S-1"),
			bank_importer.ImportResult(error="no supplier", bank_transaction="BT-1", reference_no="REF-1"),
			bank_importer.ImportResult(error="no bank account", reference_no="REF-2"),
		]

		summary = bank_importer.build_import_summary(results, "Test Company")

		self.assertEqual(summary["records"], [{"document_type": "Payment Entry", "name": "PE-1"}])
		self.assertEqual(
			summary["unreconciled"],
			[{"bank_transaction": "BT-1", "reference_no": "REF-1", "reason": "no supplier"}],
		)
		self.assertEqual(summary["errors"], ["no bank account"])
		self.assertIn("Created 1 documents (1 submitted, 0 draft)", summary["message"])
		self.assertIn("1 left unreconciled", summary["message"])
