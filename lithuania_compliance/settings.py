import frappe
from frappe.utils.caching import request_cache


def _get_setting_value(field_name: str, default=None):
	"""Fetch a field from the settings record with a fallback."""
	try:
		settings = get_settings()
		value = getattr(settings, field_name, default)
		return value if value not in (None, "") else default
	except Exception:
		return default


def get_settings():
	"""Return cached single settings doc for Lithuania compliance."""
	return frappe.get_cached_doc("Lithuania Compliance Settings")


def get_purchase_round_off_account(company: str | None = None) -> str | None:
	"""Get the configured purchase rounding account."""
	return _get_setting_value("purchase_round_off_account")


def get_sales_round_off_account(company: str | None = None) -> str | None:
	"""Get the configured sales rounding account (if needed elsewhere)."""
	return _get_setting_value("sales_round_off_account")


@request_cache
def get_sales_vat_account(company: str | None = None) -> str | None:
	"""Get the configured default Sales (output) VAT account."""
	return _get_setting_value("sales_vat_account")


@request_cache
def get_purchase_vat_account(company: str | None = None) -> str | None:
	"""Get the configured default Purchase (input) VAT account."""
	return _get_setting_value("purchase_vat_account")


@request_cache
def get_default_vat_classificator() -> str | None:
	"""Return default VAT classificator code/link value if set."""
	return _get_setting_value("default_vat_classificator")


def should_use_bill_no_as_title() -> bool:
	"""Check if Purchase Invoice should use bill_no as document title."""
	return bool(_get_setting_value("use_bill_no_as_title", False))


@request_cache
def get_ignored_item_price_codes() -> set[str]:
	"""Return item codes excluded from the Purchase Invoice Item Prices dialog."""
	try:
		settings = get_settings()
		return {row.item_code for row in (settings.get("ignored_item_price_items") or []) if row.item_code}
	except Exception:
		return set()
