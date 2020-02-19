from __future__ import unicode_literals
import frappe
from frappe import _
from .exceptions import ShopifyError
from .utils import make_magento_log
from .sync_products import make_item
from .sync_customers import create_customer
from frappe.utils import flt, nowdate, cint
from .magento_requests import get_request, get_magento_orders
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice

def sync_orders():
	sync_magento_orders()

def sync_magento_orders():
	frappe.local.form_dict.count_dict["orders"] = 0
	magento_settings = frappe.get_doc("Shopify Settings", "Shopify Settings")
	
	for magento_order in get_magento_orders():
		if valid_customer_and_product(magento_order):
			try:
				create_order(magento_order, magento_settings)
				frappe.local.form_dict.count_dict["orders"] += 1

			except ShopifyError, e:
				make_magento_log(status="Error", method="sync_magento_orders", message=frappe.get_traceback(),
					request_data=magento_order, exception=True)
			except Exception, e:
				if e.args and e.args[0] and e.args[0].decode("utf-8").startswith("402"):
					raise e
				else:
					make_magento_log(title=e.message, status="Error", method="sync_magento_orders", message=frappe.get_traceback(),
						request_data=magento_order, exception=True)
				
def valid_customer_and_product(magento_order):
	customer_id = magento_order.get("customer", {}).get("id")
	if customer_id:
		if not frappe.db.get_value("Customer", {"magento_customer_id": customer_id}, "name"):
			create_customer(magento_order.get("customer"), magento_customer_list=[])
	else:
		raise _("Customer is mandatory to create order")

	warehouse = frappe.get_doc("Shopify Settings", "Shopify Settings").warehouse
	for item in magento_order.get("line_items"):
		if not frappe.db.get_value("Item", {"magento_product_id": item.get("product_id")}, "name"):
			item = get_request("/admin/products/{}.json".format(item.get("product_id")))["product"]
			make_item(warehouse, item, magento_item_list=[])
	
	return True

def create_order(magento_order, magento_settings, company=None):
	so = create_sales_order(magento_order, magento_settings, company)
	create_sales_invoice(magento_order, magento_settings, so)
	if magento_order.get("financial_status") == "paid" and cint(magento_settings.sync_sales_invoice):
   		si = frappe.db.get_value("Sales Invoice", {"magento_order_id": magento_order.get("id")}, "name")
		si = frappe.get_doc("Sales Invoice", si)
    		si.submit()
    		make_payament_entry_against_sales_invoice(si, magento_settings)
    		frappe.db.commit()

	if magento_order.get("fulfillments") and cint(magento_settings.sync_delivery_note):
		create_delivery_note(magento_order, magento_settings, so)

def create_sales_order(magento_order, magento_settings, company=None):
	so = frappe.db.get_value("Sales Order", {"magento_order_id": magento_order.get("id")}, "name")
	if not so:
		so = frappe.get_doc({
			"doctype": "Sales Order",
			"naming_series": magento_settings.sales_order_series or "SO-Shopify-",
			"magento_order_id": magento_order.get("id"),
			"customer": frappe.db.get_value("Customer", {"magento_customer_id": magento_order.get("customer").get("id")}, "name"),
			"delivery_date": nowdate(),
			"company": magento_settings.company,
			"selling_price_list": magento_settings.price_list,
			"ignore_pricing_rule": 1,
			"items": get_order_items(magento_order.get("line_items"), magento_settings),
			"taxes": get_order_taxes(magento_order, magento_settings),
			"apply_discount_on": "Grand Total",
			"discount_amount": get_discounted_amount(magento_order),
		})
		
		if company:
			so.update({
				"company": company,
				"status": "Draft"
			})
		so.flags.ignore_mandatory = True
		so.save(ignore_permissions=True)
		so.submit()

	else:
		so = frappe.get_doc("Sales Order", so)
		
	frappe.db.commit()
	return so

def create_sales_invoice(magento_order, magento_settings, so):
	if not frappe.db.get_value("Sales Invoice", {"magento_order_id": magento_order.get("id")}, "name")\
		and so.docstatus==1 and not so.per_billed:
		si = make_sales_invoice(so.name)
		si.magento_order_id = magento_order.get("id")
		si.naming_series = magento_settings.sales_invoice_series or "SI-Shopify-"
		si.flags.ignore_mandatory = True
		set_cost_center(si.items, magento_settings.cost_center)
		si.save()
		frappe.db.commit()

def set_cost_center(items, cost_center):
	for item in items:
		item.cost_center = cost_center

def make_payament_entry_against_sales_invoice(doc, magento_settings):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
	if not doc.status == "Paid":
		payemnt_entry = get_payment_entry(doc.doctype, doc.name, bank_account=magento_settings.cash_bank_account)
		payemnt_entry.flags.ignore_mandatory = True
		payemnt_entry.reference_no = doc.name
		payemnt_entry.reference_date = nowdate()
		payemnt_entry.submit()

def create_delivery_note(magento_order, magento_settings, so):
	for fulfillment in magento_order.get("fulfillments"):
		if not frappe.db.get_value("Delivery Note", {"magento_fulfillment_id": fulfillment.get("id")}, "name")\
			and so.docstatus==1:
			dn = make_delivery_note(so.name)
			dn.magento_order_id = fulfillment.get("order_id")
			dn.magento_fulfillment_id = fulfillment.get("id")
			dn.naming_series = magento_settings.delivery_note_series or "DN-Shopify-"
			dn.items = get_fulfillment_items(dn.items, fulfillment.get("line_items"), magento_settings)
			dn.flags.ignore_mandatory = True
			dn.save()
			dn.submit()
			frappe.db.commit()

def get_fulfillment_items(dn_items, fulfillment_items, magento_settings):
	return [dn_item.update({"qty": item.get("quantity")}) for item in fulfillment_items for dn_item in dn_items\
			if get_item_code(item) == dn_item.item_code]
	
def get_discounted_amount(order):
	discounted_amount = 0.0
	for discount in order.get("discount_codes"):
		discounted_amount += flt(discount.get("amount"))
	return discounted_amount

def get_order_items(order_items, magento_settings):
	items = []
	for magento_item in order_items:
		item_code = get_item_code(magento_item)
		items.append({
			"item_code": item_code,
			"item_name": magento_item.get("name"),
			"rate": magento_item.get("price"),
			"delivery_date": nowdate(),
			"qty": magento_item.get("quantity"),
			"stock_uom": magento_item.get("sku"),
			"warehouse": magento_settings.warehouse
		})
	return items

def get_item_code(magento_item):
	item_code = frappe.db.get_value("Item", {"magento_variant_id": magento_item.get("variant_id")}, "item_code")
	if not item_code:
		item_code = frappe.db.get_value("Item", {"magento_product_id": magento_item.get("product_id")}, "item_code")

	return item_code

def get_order_taxes(magento_order, magento_settings):
	taxes = []
	for tax in magento_order.get("tax_lines"):
		taxes.append({
			"charge_type": _("On Net Total"),
			"account_head": get_tax_account_head(tax),
			"description": "{0} - {1}%".format(tax.get("title"), tax.get("rate") * 100.0),
			"rate": tax.get("rate") * 100.00,
			"included_in_print_rate": 1 if magento_order.get("taxes_included") else 0,
			"cost_center": magento_settings.cost_center
		})

	taxes = update_taxes_with_shipping_lines(taxes, magento_order.get("shipping_lines"), magento_settings)

	return taxes

def update_taxes_with_shipping_lines(taxes, shipping_lines, magento_settings):
	for shipping_charge in shipping_lines:
		taxes.append({
			"charge_type": _("Actual"),
			"account_head": get_tax_account_head(shipping_charge),
			"description": shipping_charge["title"],
			"tax_amount": shipping_charge["price"],
			"cost_center": magento_settings.cost_center
		})

	return taxes

def get_tax_account_head(tax):
	tax_title = tax.get("title").encode("utf-8")

	tax_account =  frappe.db.get_value("Shopify Tax Account", \
		{"parent": "Shopify Settings", "magento_tax": tax_title}, "tax_account")

	if not tax_account:
		frappe.throw("Tax Account not specified for Shopify Tax {0}".format(tax.get("title")))

	return tax_account
