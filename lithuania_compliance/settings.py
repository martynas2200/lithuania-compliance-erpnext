import frappe
from frappe.utils.caching import request_cache


def get_settings():
	"""Return cached single settings doc for Lithuania compliance."""
	# Using get_cached_doc ensures low DB load and auto-refresh on save
	return frappe.get_cached_doc("Lithuania Compliance Settings")


def get_purchase_round_off_account(company: str | None = None) -> str | None:
	"""Get the configured purchase rounding account."""
	try:
		settings = get_settings()
		return settings.purchase_round_off_account or None
	except Exception:
		return None


def get_sales_round_off_account(company: str | None = None) -> str | None:
	"""Get the configured sales rounding account (if needed elsewhere)."""
	try:
		settings = get_settings()
		return settings.sales_round_off_account or None
	except Exception:
		return None


@request_cache
def get_sales_vat_account(company: str | None = None) -> str | None:
	"""Get the configured default Sales (output) VAT account."""
	try:
		settings = get_settings()
		return settings.sales_vat_account or None
	except Exception:
		return None


@request_cache
def get_purchase_vat_account(company: str | None = None) -> str | None:
	"""Get the configured default Purchase (input) VAT account."""
	try:
		settings = get_settings()
		return settings.purchase_vat_account or None
	except Exception:
		return None


@request_cache
def get_default_vat_classificator() -> str | None:
	"""Return default VAT classificator code/link value if set."""
	try:
		settings = get_settings()
		return settings.default_vat_classificator or None
	except Exception:
		return None


def should_use_bill_no_as_title() -> bool:
	"""Check if Purchase Invoice should use bill_no as document title."""
	try:
		settings = get_settings()
		return bool(getattr(settings, "use_bill_no_as_title", False))
	except Exception:
		return False
