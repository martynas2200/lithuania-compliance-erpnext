import re

import frappe
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from . import settings as lt_settings


class CustomPurchaseInvoice(PurchaseInvoice):
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
