"""Helpers and API for Purchase Invoice."""

from datetime import datetime

import frappe


def _add_supplier_for_items(doc):
	"""
	Ensure invoice supplier is in each Item's supplier list.

	For every item row in the Purchase Invoice, this job loads the
	corresponding Item and, if the invoice supplier is not already
	listed in the Item's ``supplier_items`` child table, appends a new
	row and saves the Item.
	"""
	supplier = getattr(doc, "supplier", None)
	if not supplier:
		return

	processed_items = set()

	for item in getattr(doc, "items", []) or []:
		item_code = getattr(item, "item_code", None)
		if not item_code or item_code in processed_items:
			continue

		processed_items.add(item_code)

		try:
			item_doc = frappe.get_doc("Item", item_code)
		except frappe.DoesNotExistError:
			# If the item no longer exists, just skip it
			continue

		existing_suppliers = {
			row.supplier
			for row in (getattr(item_doc, "supplier_items", []) or [])
			if getattr(row, "supplier", None)
		}

		if supplier not in existing_suppliers:
			item_doc.append("supplier_items", {"supplier": supplier})
			item_doc.save(ignore_permissions=True)
			frappe.db.commit()


def enqueue_supplier_items_sync(doc, method=None):
	"""Enqueue background job to validate suppliers on submit.

	Hook signature: ``doc, method``.
	"""
	frappe.enqueue(
		"lithuania_compliance.api.purchase_invoice._add_supplier_for_items",
		doc=doc,
		queue="short",
		now=False,
	)


@frappe.whitelist()
def get_item_prices(invoice_name):
	"""
	Get prices for all items in a Purchase Invoice.

	Logic for determining applicable price when multiple are valid:
	1. Filter prices where today's date falls between valid_from and valid_upto
	2. If multiple prices are applicable, select the one with the latest valid_from date
	   (newer price overrides older price)
	3. Return both applicable price and other valid prices for reference

	Args:
		invoice_name: Name of the Purchase Invoice

	Returns:
		List of dicts with item info and applicable prices
	"""
	invoice = frappe.get_doc("Purchase Invoice", invoice_name)
	today = datetime.today().date()

	items_data = []

	for item in invoice.items:
		item_code = item.item_code

		prices = frappe.get_list(
			"Item Price",
			filters={
				"item_code": item_code,
				"selling": 1,
			},
			fields=["name", "price_list_rate", "currency", "valid_from", "valid_upto", "price_list"],
			order_by="valid_from desc",  # Newest first
		)

		applicable_price = None
		other_valid_prices = []

		for price in prices:
			valid_from = price.get("valid_from")
			valid_upto = price.get("valid_upto")

			# Check if price is currently valid
			is_valid = True

			if valid_from:
				valid_from_date = frappe.utils.getdate(valid_from)
				if today < valid_from_date:
					is_valid = False

			if valid_upto:
				valid_upto_date = frappe.utils.getdate(valid_upto)
				if today > valid_upto_date:
					is_valid = False

			if is_valid:
				# If no applicable price yet, this becomes applicable
				# (because list is ordered by valid_from desc, first valid is the newest)
				if not applicable_price:
					applicable_price = price
				else:
					# Additional valid prices
					other_valid_prices.append(price)
			else:
				# Future or expired prices
				other_valid_prices.append(price)

		# Calculate markup if applicable price exists
		markup = 0
		if applicable_price and item.rate:
			applicable_rate = applicable_price.get("price_list_rate", 0)
			if item.rate > 0:
				# Adding 21% VAT to the base price
				# TODO: Add a setting for VAT rate or if we plan to use clasificators for each item.
				cost_with_vat = item.rate * 1.21
				markup = ((applicable_rate - cost_with_vat) / cost_with_vat) * 100

		items_data.append(
			{
				"item_code": item_code,
				"item_name": item.item_name,
				"rate": item.rate,
				"markup": round(markup, 2),
				"applicable_price": applicable_price,
				"other_valid_prices": other_valid_prices,
			}
		)

	return items_data
