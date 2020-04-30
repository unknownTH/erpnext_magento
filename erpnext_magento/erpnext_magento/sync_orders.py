from __future__ import unicode_literals
import frappe
from frappe import _
from erpnext_magento.erpnext_magento.exceptions import MagentoError
from erpnext_magento.erpnext_magento.utils import make_magento_log
from erpnext_magento.erpnext_magento.sync_customers import sync_magento_customer_addresses
from frappe.utils import flt, nowdate, cint
from erpnext_magento.erpnext_magento.magento_requests import (
	get_request,
	get_magento_orders,
	get_magento_order_invoices,
	get_magento_order_shipments,
	get_magento_website_name_by_store_id
)
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

def sync_orders():
	magento_order_list = []
	sync_magento_orders(magento_order_list)
	frappe.local.form_dict.count_dict["erpnext_orders"] = len(magento_order_list)

def sync_magento_orders(magento_order_list):
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	for magento_order in get_magento_orders():
		if magento_order.get("customer_is_guest") == 1:
			magento_order.update({"erpnext_guest_customer_name": get_erpnext_guest_customer_name(magento_order, magento_settings)})

		try:
			if not frappe.db.get_value("Sales Order", {"magento_order_id": magento_order.get("entity_id")}, "name"):
				create_erpnext_sales_order(magento_order, magento_settings)
			
			if cint(magento_settings.sync_delivery_note):
				sync_magento_shipments(magento_order, magento_settings)
			
			if cint(magento_settings.sync_sales_invoice):
				sync_magento_invoices(magento_order, magento_settings)

			magento_order_list.append(magento_order.get("entity_id"))

		except MagentoError as e:
			make_magento_log(status="Error", method="sync_magento_orders", message=frappe.get_traceback(),
				request_data=magento_order, exception=True)
	
		except Exception as e:
			if e.args and e.args[0] and e.args[0].decode("utf-8").startswith("402"):
				raise e
			else:
				make_magento_log(title=e.message, status="Error", method="sync_magento_orders", message=frappe.get_traceback(),
					request_data=magento_order, exception=True)
			
def get_erpnext_guest_customer_name(magento_order, magento_settings):
	erpnext_guest_customer_name = frappe.db.get_value("Customer", {"magento_customer_email": magento_order.get("customer_email")}, "name")
	erpnext_guest_customer_dict = {
		"doctype": "Customer",
		"customer_first_name": magento_order.get("customer_firstname"),
		"customer_last_name": magento_order.get("customer_lastname"),
		"customer_name": f'{magento_order.get("customer_firstname")} {magento_order.get("customer_lastname")}',
		"magento_customer_email" : magento_order.get("customer_email"),
		"customer_group": magento_settings.customer_group,
		"customer_details": "Magento Guest",
		"territory": frappe.utils.nestedset.get_root_of("Territory"),
		"customer_type": _("Individual")
	}

	try:
		if not erpnext_guest_customer_name:
			erpnext_guest_customer = frappe.get_doc(erpnext_guest_customer_dict)
			erpnext_guest_customer.flags.ignore_mandatory = True
			erpnext_guest_customer.insert()
			frappe.db.commit()

		else:
			erpnext_guest_customer = frappe.get_doc("Customer", erpnext_guest_customer_name)
			erpnext_guest_customer.update(erpnext_guest_customer_dict)
			erpnext_guest_customer.flags.ignore_mandatory = True
			erpnext_guest_customer.save()
			frappe.db.commit()

		sync_erpnext_guest_customer_adresses(erpnext_guest_customer, magento_order)

	except Exception as e:
		make_magento_log(title=e.message, status="Error", method="get_erpnext_guest_customer_name", message=frappe.get_traceback(),
			request_data=magento_order, exception=True)

	return erpnext_guest_customer.name

def sync_erpnext_guest_customer_adresses(erpnext_guest_customer, magento_order):
	magento_order_addresses = []
	magento_order_addresses.append(magento_order.get("billing_address"))
	magento_order_addresses.append(magento_order.get("extension_attributes").get("shipping_assignments")[0].get("shipping").get("address"))

	sync_magento_customer_addresses(erpnext_guest_customer, magento_order_addresses)

def create_erpnext_sales_order(magento_order, magento_settings):
	erpnext_sales_order = frappe.get_doc({
		"doctype": "Sales Order",
		"naming_series": magento_settings.sales_order_series or "SO-MAGENTO-",
		"magento_order_id": magento_order.get("entity_id"),
		"magento_payment_method": magento_order.get("payment").get("method"),
		"customer": magento_order.get("erpnext_guest_customer_name") or frappe.db.get_value("Customer", {"magento_customer_id": magento_order.get("customer_id")}, "name"),
		"delivery_date": nowdate(),
		"company": magento_settings.company,
		"selling_price_list": get_price_list(magento_order, magento_settings),
		"ignore_pricing_rule": 1,
		"items": get_order_items(magento_order.get("items"), magento_settings),
		"taxes": get_order_taxes(magento_order, magento_settings),
		"apply_discount_on": "Grand Total",
		"discount_amount": magento_order.get("discount_amount")
	})
	
	erpnext_sales_order.flags.ignore_mandatory = True
	erpnext_sales_order.save()
	erpnext_sales_order.submit()	
	frappe.db.commit()

def get_price_list(magento_order, magento_settings):
	for price_list in magento_settings.price_lists:
		if price_list.magento_website_name == get_magento_website_name_by_store_id(magento_order.get("store_id")):
			return price_list.price_list

def get_order_items(order_items, magento_settings):
	items = []

	for magento_item in order_items:
		if magento_item.get("product_type") != "configurable":
			items.append({
				"item_code": frappe.db.get_value("Item", {"magento_product_id": magento_item.get("product_id")}, "item_code"),
				"item_name": magento_item.get("name"),
				"rate": magento_item.get("base_original_price"),
				"delivery_date": nowdate(),
				"qty": magento_item.get("qty_ordered"),
				"magento_sku": magento_item.get("sku"),
			})

	return items

def get_order_taxes(magento_order, magento_settings):
	taxes = []

	for tax in magento_order.get("extension_attributes").get("applied_taxes"):
		taxes.append({
			"charge_type": _("On Net Total"),
			"account_head": get_tax_account_head(tax),
			"description": f'{tax.get("code")} - {tax.get("percent")}%',
			"rate": tax.get("percent"),
			"included_in_print_rate": 1,
			"cost_center": magento_settings.cost_center
		})

	return taxes

def get_tax_account_head(tax):
	tax_account =  frappe.db.get_value("Magento Tax Account", {"parent": "Magento Settings", "magento_tax": tax.get("code")}, "tax_account")

	if not tax_account:
		frappe.throw(f'Tax Account not specified for Magento Tax {tax.get("code")}')

	return tax_account

def sync_magento_shipments(magento_order, magento_settings):
	erpnext_sales_order_name = frappe.db.get_value("Sales Order", {"magento_order_id": magento_order.get("entity_id")}, "name")
	erpnext_sales_order = frappe.get_doc("Sales Order", erpnext_sales_order_name)

	for shipment in get_magento_order_shipments(magento_order.get("entity_id")):
		if not frappe.db.get_value("Delivery Note", {"magento_shipment_id": shipment.get("entity_id")}, "name")	and erpnext_sales_order.docstatus == 1:
			delivery_note = make_delivery_note(erpnext_sales_order.name)
			delivery_note.magento_order_id = shipment.get("order_id")
			delivery_note.magento_shipment_id = shipment.get("entity_id")
			delivery_note.naming_series = magento_settings.delivery_note_series or "delivery_note-Magento-"
			delivery_note.items = get_magento_shipment_items(delivery_note.items, shipment.get("items"), magento_settings)
			delivery_note.flags.ignore_mandatory = True
			delivery_note.save()
			delivery_note.submit()
			frappe.db.commit()

def get_magento_shipment_items(delivery_note_items, shipment_items, magento_settings):
	return [delivery_note_item.update({"qty": item.get("qty_shipped")}) for item in shipment_items for delivery_note_item in delivery_note_items\
			if frappe.db.get_value("Item", {"magento_product_id": item.get("product_id")}, "item_code") == delivery_note_item.item_code]

def sync_magento_invoices(magento_order, magento_settings):
	erpnext_sales_order_name = frappe.db.get_value("Sales Order", {"magento_order_id": magento_order.get("entity_id")}, "name")
	erpnext_sales_order = frappe.get_doc("Sales Order", erpnext_sales_order_name)

	for invoice in get_magento_order_invoices(magento_order.get("entity_id")):
		erpnext_sales_invoice_name = frappe.db.get_value("Sales Invoice", {"magento_order_id": magento_order.get("entity_id")}, "name")
		
		if not erpnext_sales_invoice_name and erpnext_sales_order.docstatus==1:
			erpnext_sales_invoice = make_sales_invoice(erpnext_sales_order.name)
			erpnext_sales_invoice.magento_order_id = magento_order.get("entity_id")
			erpnext_sales_invoice.naming_series = magento_settings.sales_invoice_series or "erpnext_sales_invoice-Magento-"
			erpnext_sales_invoice.flags.ignore_mandatory = True
			set_cost_center(erpnext_sales_invoice.items, magento_settings.cost_center)
			erpnext_sales_invoice.save()
			frappe.db.commit()
		
		else:
			erpnext_sales_invoice = frappe.get_doc("Sales Invoice", erpnext_sales_invoice_name)

		if invoice.get("state") == 2:
			erpnext_sales_invoice.submit()
			frappe.db.commit()

			make_payament_entry_against_sales_invoice(erpnext_sales_invoice, magento_settings)

def set_cost_center(items, cost_center):
	for item in items:
		item.cost_center = cost_center

def make_payament_entry_against_sales_invoice(doc, magento_settings):
	if not doc.status == "Paid":
		payemnt_entry = get_payment_entry(doc.doctype, doc.name, bank_account=magento_settings.cash_bank_account)
		payemnt_entry.flags.ignore_mandatory = True
		payemnt_entry.reference_no = doc.name
		payemnt_entry.reference_date = nowdate()
		payemnt_entry.submit()
		frappe.db.commit()
