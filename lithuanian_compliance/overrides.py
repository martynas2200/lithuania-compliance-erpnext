import frappe
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice

from . import settings as lt_settings


class CustomPurchaseInvoice(PurchaseInvoice):
	def get_gl_entries(self, warehouse_account=None):
		gl_entries = super().get_gl_entries(warehouse_account)

		# Fetch configured purchase rounding account from app settings
		purchase_round_off_account = lt_settings.get_purchase_round_off_account()

		# Get the company's default round-off account from Company settings
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
