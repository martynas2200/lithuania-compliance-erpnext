import re

import frappe
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from . import settings as lt_settings

STANDARD_INVOICE_TYPES = ["SF", "VS"]
RETURN_REQUIRING_INVOICE_TYPES = ["DS", "KS", "VD", "VK"]


class CustomPurchaseInvoice(PurchaseInvoice):
	def _validate_and_set_is_return(self):
		"""Check if invoice type requires is_return flag and set it automatically."""
		invoice_type = getattr(self, "invoice_type_lt", None)
		if invoice_type and any(code in invoice_type for code in RETURN_REQUIRING_INVOICE_TYPES):
			if not self.is_return:
				self.is_return = 1
				frappe.msgprint(
					"This invoice type requires 'Is Returned' to be checked. It has been automatically marked."
				)
		if invoice_type and any(code in invoice_type for code in STANDARD_INVOICE_TYPES):
			if self.is_return:
				self.is_return = 0
				frappe.msgprint(
					"This invoice type does not allow 'Is Returned' to be checked. It has been automatically unmarked."
				)

	def before_insert(self):
		"""Set document name to bill_no and first two supplier words if enabled."""
		if lt_settings.should_use_bill_no_as_title() and getattr(self, "bill_no", None):
			title = self.bill_no
			supplier_source = getattr(self, "supplier_name", None) or getattr(self, "supplier", None)
			if supplier_source:
				cleaned = re.sub(r"[^\w\s]", "", supplier_source)
				words = cleaned.split()
				if words:
					title = f"{title} {' '.join(words[:2])}"
			self.title = title

		self._validate_and_set_is_return()

	def before_save(self):
		"""Validate invoice type and is_return flag on every save."""
		self._validate_and_set_is_return()

	def get_gl_entries(self, warehouse_account=None):
		gl_entries = super().get_gl_entries(warehouse_account)

		purchase_round_off_account = lt_settings.get_purchase_round_off_account()

		company_round_off_account = None
		if getattr(self, "company", None):
			company_round_off_account = frappe.get_cached_value("Company", self.company, "round_off_account")

		# Iterate through GL entries and rewrite the round-off line
		if company_round_off_account and purchase_round_off_account:
			for gle in gl_entries:
				if gle.get("account") == company_round_off_account:
					gle["account"] = purchase_round_off_account
					gle["account_currency"] = frappe.db.get_value(
						"Account", purchase_round_off_account, "account_currency"
					)
		return gl_entries


class CustomSalesInvoice(SalesInvoice):
	def _validate_and_set_is_return(self):
		"""Check if invoice type requires is_return flag and set it automatically."""
		invoice_type = getattr(self, "invoice_type_lt", None)
		if invoice_type and any(code in invoice_type for code in RETURN_REQUIRING_INVOICE_TYPES):
			if not self.is_return:
				self.is_return = 1
				frappe.msgprint(
					"This invoice type requires 'Is Returned' to be checked. It has been automatically marked."
				)
		if invoice_type and any(code in invoice_type for code in STANDARD_INVOICE_TYPES):
			if self.is_return:
				self.is_return = 0
				frappe.msgprint(
					"This invoice type does not allow 'Is Returned' to be checked. It has been automatically unmarked."
				)

	def before_insert(self):
		self._validate_and_set_is_return()

	def before_save(self):
		"""Validate invoice type and is_return flag on every save."""
		self._validate_and_set_is_return()

	def get_gl_entries(self, warehouse_account=None):
		gl_entries = super().get_gl_entries(warehouse_account)

		sales_round_off_account = lt_settings.get_sales_round_off_account()

		company_round_off_account = None
		if getattr(self, "company", None):
			company_round_off_account = frappe.get_cached_value("Company", self.company, "round_off_account")

		# Iterate through GL entries and rewrite the round-off line
		if company_round_off_account and sales_round_off_account:
			for gle in gl_entries:
				if gle.get("account") == company_round_off_account:
					gle["account"] = sales_round_off_account
					gle["account_currency"] = frappe.db.get_value(
						"Account", sales_round_off_account, "account_currency"
					)
		return gl_entries
