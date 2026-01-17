import json
import os

import frappe


def _load_json(joins: list[str]) -> dict | list | None:
	"""Load a JSON list from a file within this app if it exists."""
	path = frappe.get_app_path("lithuania_compliance", *joins)
	if not os.path.exists(path):
		return None
	try:
		with open(path) as f:
			return json.load(f)
	except Exception as e:
		frappe.log_error(f"Failed reading JSON: {path}: {e}", "lithuania_compliance install")
		return None


def seed_vat_classificators() -> None:
	"""Create/Update VAT Classificators from defaults.json if present.

	File location: lithuania_compliance/doctype/vat_classificator/defaults.json
	Expected format: a JSON array of objects with keys: code (str), description (str, optional)
	Any additional keys will be ignored.
	"""
	rows = _load_json(
		[
			"lithuania_compliance",
			"doctype",
			"vat_classificator",
			"defaults.json",
		]
	)
	if not rows:
		return

	for row in rows:
		if not row.get("code"):
			continue
		code = row.get("code")
		rate = None
		exempt = 0
		raw_value = row.get("value")
		if raw_value is None:
			exempt = 1
		else:
			try:
				rate = float(raw_value)
			except (TypeError, ValueError):
				rate = None

		description = row.get("description") or ""

		if not frappe.db.exists("VAT Classificator", code):
			frappe.get_doc(
				{
					"doctype": "VAT Classificator",
					"code": code,
					"is_exempt": exempt,
					"description": description,
					"rate": rate,
				}
			).insert(ignore_permissions=True)


def ensure_default_settings() -> None:
	"""If settings exist and default classificator is empty, set a sensible default."""
	try:
		settings = frappe.get_single("Lithuania Compliance Settings")
		if not settings.default_vat_classificator and frappe.db.exists("VAT Classificator", "PVM1"):
			settings.default_vat_classificator = "PVM1"
			settings.save(ignore_permissions=True)
	except Exception:
		# ignore if settings not installed yet
		pass


def after_install():
	seed_vat_classificators()
	ensure_default_settings()


def after_migrate():
	# Keep newly added defaults in sync on future app updates
	seed_vat_classificators()
	ensure_default_settings()
