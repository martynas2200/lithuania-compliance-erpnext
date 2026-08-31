"""
Unit tests for ``lithuania_compliance.api.isaf.get_document_totals``.
Quite a divergence from usual Frappe testing flow since all DB-backed helpers are mocked.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from lithuania_compliance.api import isaf
from lithuania_compliance.api.isaf import get_document_totals

PURCHASE_VAT_ACCOUNT = "Gautinas pridėtinės vertės mokestis"


def vat_doc(rate=None, is_exempt=False):
	"""Build a minimal stand-in for a VAT Classificator doc."""
	return SimpleNamespace(rate=rate, is_exempt=is_exempt)


_INVOICE_ITEMS = [
	("ncc8n5rjok", "P1969", 9.84),
	("nccbe8rfkc", "P1973", 6.68),
	("nccjj4duj9", "P1949", 5.88),
	("ncc0hcir6v", "P1947", 3.08),
	("nccjrcerl0", "P1966", 2.94),
	("ncc1ph1tbv", "P1967", 3.06),
	("nccq7ss3or", "P1952", 2.70),
]

# item_row -> amount (VAT at 21%)
_INVOICE_TAX_DETAILS = {
	"ncc8n5rjok": 2.07,
	"nccbe8rfkc": 1.40,
	"nccjj4duj9": 1.23,
	"ncc0hcir6v": 0.65,
	"nccjrcerl0": 0.62,
	"ncc1ph1tbv": 0.64,
	"nccq7ss3or": 0.57,
}


def build_invoice_items():
	"""Return the items child-table rows for the shared invoice fixture."""
	return [
		{
			"name": name,
			"item_code": item_code,
			"base_amount": base_amount,
		}
		for name, item_code, base_amount in _INVOICE_ITEMS
	]


def build_invoice_taxes():
	"""Return the single automatic (On Net Total) tax row."""
	return [
		{
			"name": "skcov1488l",
			"charge_type": "On Net Total",
			"account_head": PURCHASE_VAT_ACCOUNT,
			"vat_classificator": None,
			"tax_amount": 7.18,
		}
	]


def build_item_wise_tax_details():
	"""Return the per-item VAT breakdown for the shared invoice fixture."""
	return [
		{
			"item_row": item_row,
			"tax_row": "skcov1488l",
			"taxable_amount": base_amount,
			"amount": amount,
		}
		for (name, item_code, base_amount), (item_row, amount) in zip(
			_INVOICE_ITEMS, _INVOICE_TAX_DETAILS.items(), strict=True
		)
	]


def _patch_helpers(default_classificator="PVM1", classificators=None, item_classificators=None):
	"""
	Patch the DB-backed helpers used by get_document_totals.

	classificators: dict code -> vat_doc
	item_classificators: dict item_code -> classificator code (or None)
	"""
	classificators = classificators or {
		"PVM1": vat_doc(rate=21),
		"PVM100": vat_doc(rate=None, is_exempt=True),
	}
	item_classificators = item_classificators or {}

	def fake_get_vat_classificator(tax_code):
		return classificators.get(tax_code)

	def fake_get_item_vat_classificator(item_code):
		return item_classificators.get(item_code)

	return (
		# default vat classificator from settings
		patch.object(isaf.lt_settings, "get_default_vat_classificator", return_value=default_classificator),
		# VAT Classificator doc lookup
		patch.object(isaf, "get_vat_classificator", side_effect=fake_get_vat_classificator),
		# Item-level VAT classificator lookup
		patch.object(isaf, "get_item_vat_classificator", side_effect=fake_get_item_vat_classificator),
	)


class TestGetDocumentTotalsNativeFlow(unittest.TestCase):
	"""The native automatic VAT flow (the PIRK-26-08-108 scenario)."""

	def test_single_rate_invoice_totals(self):
		"""The full shared invoice produces one PVM1 row with the expected values."""
		patchers = _patch_helpers()
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		result = get_document_totals(
			items=build_invoice_items(),
			taxes=build_invoice_taxes(),
			rounding=0.0,
			item_wise_tax_details=build_item_wise_tax_details(),
			vat_account=PURCHASE_VAT_ACCOUNT,
		)

		self.assertEqual(len(result), 1)
		line = result[0]
		self.assertEqual(line["tax_code"], "PVM1")
		self.assertEqual(line["taxable_value"], 34.18)
		self.assertEqual(line["amount"], 7.18)
		self.assertEqual(line["tax_percentage"], 21)

	def test_non_vat_tax_row_is_ignored(self):
		"""Automatic tax rows on accounts other than the VAT account are excluded."""
		patchers = _patch_helpers()
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		taxes = [
			*build_invoice_taxes(),
			{
				"name": "tax_fee",
				"charge_type": "On Net Total",
				"account_head": "6100 - Įvairios paslaugos - SMPĮ",
				"vat_classificator": None,
				"tax_amount": 5.00,
			},
		]

		result = get_document_totals(
			items=build_invoice_items(),
			taxes=taxes,
			rounding=0.0,
			item_wise_tax_details=build_item_wise_tax_details(),
			vat_account=PURCHASE_VAT_ACCOUNT,
		)

		self.assertEqual(len(result), 1)
		# Only the VAT account row's amount is counted.
		self.assertEqual(result[0]["amount"], 7.18)

	def test_taxable_value_counted_once_per_item_row(self):
		"""taxable_value is counted once per item_row, but amount is summed."""
		patchers = _patch_helpers()
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		items = [
			{"name": "row1", "item_code": "P1969", "base_amount": 10.00},
		]
		details = [
			{"item_row": "row1", "tax_row": "skcov1488l", "taxable_amount": 10.00, "amount": 1.05},
			{"item_row": "row1", "tax_row": "skcov1488l", "taxable_amount": 10.00, "amount": 1.05},
		]

		result = get_document_totals(
			items=items,
			taxes=build_invoice_taxes(),
			rounding=0.0,
			item_wise_tax_details=details,
			vat_account=PURCHASE_VAT_ACCOUNT,
		)

		self.assertEqual(len(result), 1)
		# taxable_value counted once despite two rows
		self.assertEqual(result[0]["taxable_value"], 10.00)
		self.assertEqual(result[0]["amount"], 2.10)

	def test_item_level_classificator_overrides_default(self):
		"""An item's own vat_classificator wins over the default."""
		patchers = _patch_helpers(classificators={"PVM2": vat_doc(rate=9)})
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		items = [
			{"name": "row1", "item_code": "P0001", "base_amount": 50.00, "vat_classificator": "PVM2"},
		]
		details = [
			{"item_row": "row1", "tax_row": "skcov1488l", "taxable_amount": 50.00, "amount": 4.50},
		]

		result = get_document_totals(
			items=items,
			taxes=build_invoice_taxes(),
			rounding=0.0,
			item_wise_tax_details=details,
			vat_account=PURCHASE_VAT_ACCOUNT,
		)

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["tax_code"], "PVM2")
		self.assertEqual(result[0]["tax_percentage"], 9)
		self.assertEqual(result[0]["amount"], 4.50)


class TestGetDocumentTotalsActualFlow(unittest.TestCase):
	"""The fallback flow using explicit 'Actual' tax rows."""

	def test_actual_tax_rows_grouped_by_classificator(self):
		"""Items grouped by classificator, tax amounts added from Actual rows."""
		patchers = _patch_helpers(classificators={"PVM1": vat_doc(rate=21)})
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		items = [
			{"name": "row1", "item_code": "P1969", "base_amount": 100.00},
			{"name": "row2", "item_code": "P1973", "base_amount": 50.00},
		]
		taxes = [
			{
				"name": "t1",
				"charge_type": "Actual",
				"account_head": PURCHASE_VAT_ACCOUNT,
				"vat_classificator": "PVM1",
				"tax_amount": 31.50,
			}
		]

		result = get_document_totals(
			items=items,
			taxes=taxes,
			rounding=0.0,
			item_wise_tax_details=[],
			vat_account=PURCHASE_VAT_ACCOUNT,
		)

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["tax_code"], "PVM1")
		self.assertEqual(result[0]["taxable_value"], 150.00)
		self.assertEqual(result[0]["amount"], 31.50)
		self.assertEqual(result[0]["tax_percentage"], 21)

	def test_multiple_tax_codes(self):
		"""Items/taxes split across two classificators produce two rows."""
		patchers = _patch_helpers(classificators={"PVM1": vat_doc(rate=21), "PVM2": vat_doc(rate=9)})
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		items = [
			{"name": "row1", "item_code": "P0001", "base_amount": 100.00, "vat_classificator": "PVM1"},
			{"name": "row2", "item_code": "P0002", "base_amount": 100.00, "vat_classificator": "PVM2"},
		]
		taxes = [
			{"name": "t1", "charge_type": "Actual", "vat_classificator": "PVM1", "tax_amount": 21.00},
			{"name": "t2", "charge_type": "Actual", "vat_classificator": "PVM2", "tax_amount": 9.00},
		]

		result = get_document_totals(
			items=items,
			taxes=taxes,
			rounding=0.0,
			item_wise_tax_details=[],
			vat_account=None,
		)

		by_code = {line["tax_code"]: line for line in result}
		self.assertEqual(set(by_code), {"PVM1", "PVM2"})
		self.assertEqual(by_code["PVM1"]["taxable_value"], 100.00)
		self.assertEqual(by_code["PVM1"]["amount"], 21.00)
		self.assertEqual(by_code["PVM2"]["taxable_value"], 100.00)
		self.assertEqual(by_code["PVM2"]["amount"], 9.00)


class TestGetDocumentTotalsRounding(unittest.TestCase):
	"""Rounding adjustment handling (accountant requirements)."""

	def _run(self, items, taxes, rounding):
		patchers = _patch_helpers()
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		return get_document_totals(
			items=items,
			taxes=taxes,
			rounding=rounding,
			item_wise_tax_details=[],
			vat_account=PURCHASE_VAT_ACCOUNT,
		)

	def _actual_items(self):
		return [
			{"name": "row1", "item_code": "P1969", "base_amount": 100.00},
		]

	def _actual_taxes(self):
		return [
			{"name": "t1", "charge_type": "Actual", "vat_classificator": "PVM1", "tax_amount": 21.00},
		]

	def test_positive_rounding_creates_pvm100_row(self):
		result = self._run(self._actual_items(), self._actual_taxes(), rounding=0.02)
		by_code = {line["tax_code"]: line for line in result}
		self.assertIn("PVM100", by_code)
		self.assertEqual(by_code["PVM100"]["taxable_value"], 0.02)
		self.assertEqual(by_code["PVM100"]["tax_percentage"], None)

	def test_negative_rounding_with_pvm100_adds_to_pvm100(self):
		"""Negative rounding with an existing PVM100 row folds into PVM100."""
		patchers = _patch_helpers()
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		# Include an exempt item assigned PVM100 so that PVM100 is already in the summary.
		items = [
			{"name": "row1", "item_code": "P1969", "base_amount": 100.00},
			{"name": "row2", "item_code": "P0100", "base_amount": 10.00, "vat_classificator": "PVM100"},
		]
		taxes = [
			{"name": "t1", "charge_type": "Actual", "vat_classificator": "PVM1", "tax_amount": 21.00},
		]

		result = get_document_totals(
			items=items,
			taxes=taxes,
			rounding=-0.02,
			item_wise_tax_details=[],
			vat_account=PURCHASE_VAT_ACCOUNT,
		)
		by_code = {line["tax_code"]: line for line in result}
		self.assertIn("PVM100", by_code)
		self.assertEqual(by_code["PVM100"]["taxable_value"], 9.98)
		self.assertEqual(by_code["PVM1"]["taxable_value"], 100.00)

	def test_negative_rounding_without_pvm100_reduces_pvm1(self):
		"""Negative rounding without PVM100 reduces the PVM1 taxable value (no negative row)."""
		result = self._run(self._actual_items(), self._actual_taxes(), rounding=-0.02)
		by_code = {line["tax_code"]: line for line in result}
		self.assertNotIn("PVM100", by_code)
		self.assertEqual(by_code["PVM1"]["taxable_value"], 99.98)

	def test_no_rounding_no_effect(self):
		result = self._run(self._actual_items(), self._actual_taxes(), rounding=0.0)
		by_code = {line["tax_code"]: line for line in result}
		self.assertNotIn("PVM100", by_code)
		self.assertEqual(by_code["PVM1"]["taxable_value"], 100.00)


class TestGetDocumentTotalsDiscrepancies(unittest.TestCase):
	"""Validation that raises on VAT discrepancies."""

	def test_throws_when_percentage_positive_but_amount_zero(self):
		patchers = _patch_helpers()
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		items = [{"name": "row1", "item_code": "P1969", "base_amount": 100.00}]
		taxes = [
			{"name": "t1", "charge_type": "Actual", "vat_classificator": "PVM1", "tax_amount": 0.0},
		]

		with self.assertRaises(frappe.ValidationError):
			get_document_totals(
				items=items,
				taxes=taxes,
				rounding=0.0,
				item_wise_tax_details=[],
				vat_account=PURCHASE_VAT_ACCOUNT,
			)

	def test_throws_when_rate_mismatch_exceeds_tolerance(self):
		patchers = _patch_helpers()
		for p in patchers:
			p.start()
		self.addCleanup(lambda: [p.stop() for p in patchers])

		items = [{"name": "row1", "item_code": "P1969", "base_amount": 100.00}]
		taxes = [
			{"name": "t1", "charge_type": "Actual", "vat_classificator": "PVM1", "tax_amount": 5.00},
		]

		with self.assertRaises(frappe.ValidationError):
			get_document_totals(
				items=items,
				taxes=taxes,
				rounding=0.0,
				item_wise_tax_details=[],
				vat_account=PURCHASE_VAT_ACCOUNT,
			)


if __name__ == "__main__":
	unittest.main()
