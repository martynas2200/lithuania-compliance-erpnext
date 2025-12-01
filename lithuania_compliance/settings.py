import frappe


def get_settings():
	"""Return cached single settings doc for Lithuania compliance."""
	# Using get_cached_doc ensures low DB load and auto-refresh on save
	return frappe.get_cached_doc("Lithuania Compliance Settings")


def get_purchase_round_off_account(company: str | None = None) -> str | None:
	"""Get the configured purchase rounding account.

	Args:
	    company: Reserved for future company-specific handling. Not used yet.

	Returns:
	    The Account name or None if not set.
	"""
	try:
		settings = get_settings()
		return settings.purchase_round_off_account or None
	except Exception:
		# Settings might not exist during install/migrate
		return None


def get_sales_round_off_account(company: str | None = None) -> str | None:
	"""Get the configured sales rounding account (if needed elsewhere)."""
	try:
		settings = get_settings()
		return settings.sales_round_off_account or None
	except Exception:
		return None


def get_default_pvm_classificator() -> str | None:
	"""Return default PVM classificator code/link value if set."""
	try:
		settings = get_settings()
		return settings.default_pvm_classificator or None
	except Exception:
		return None


def get_item_pvm_classificator(item_code: str) -> str | None:
	"""Resolve PVM classificator for an Item, falling back to default.

	Looks up the mapping table on the settings doc. If an explicit mapping for
	the Item exists, returns that classificator; otherwise returns the default.
	"""
	try:
		settings = get_settings()
		# iterate child table rows if any
		for row in settings.pvm_item_map or []:
			if getattr(row, "item", None) == item_code:
				return getattr(row, "pvm_classificator", None) or get_default_pvm_classificator()
		return get_default_pvm_classificator()
	except Exception:
		return None


def should_use_bill_no_as_title() -> bool:
	"""Check if Purchase Invoice should use bill_no as document title."""
	try:
		settings = get_settings()
		return bool(getattr(settings, "use_bill_no_as_title", False))
	except Exception:
		return False
