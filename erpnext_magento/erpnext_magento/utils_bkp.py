# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import frappe
from frappe import throw, _
import json
from erpnext_magento.erpnext_magento.exceptions import MagentoSetupError

def disable_magento_sync_for_item(item, rollback=False):
	"""Disable Item if not exist on magento"""
	if rollback:
		frappe.db.rollback()
		
	item.sync_with_magento = 0
	item.sync_qty_with_magento = 0
	item.save(ignore_permissions=True)
	frappe.db.commit()

def disable_magento_sync_on_exception():
	frappe.db.rollback()
	frappe.db.set_value("Magento Settings", None, "enable_magento", 0)
	frappe.db.commit()

def is_magento_enabled():
	magento_settings = frappe.get_doc("Magento Settings")
	if not magento_settings.enable_magento:
		return False
	try:
		magento_settings.validate()
	except MagentoSetupError:
		return False
	
	return True
	
def make_magento_log(title="Sync Log", status="Queued", method="sync_magento", message=None, exception=False, 
name=None, request_data={}):
	if not name:
		name = frappe.db.get_value("Magento Log", {"status": "Queued"})
		
		if name:
			""" if name not provided by log calling method then fetch existing queued state log"""
			log = frappe.get_doc("Magento Log", name)
		
		else:
			""" if queued job is not found create a new one."""
			log = frappe.get_doc({"doctype":"Magento Log"}).insert(ignore_permissions=True)
		
		if exception:
			frappe.db.rollback()
			log = frappe.get_doc({"doctype":"Magento Log"}).insert(ignore_permissions=True)
			
		log.message = message if message else frappe.get_traceback()
		log.title = title[0:140]
		log.method = method
		log.status = status
		log.request_data= json.dumps(request_data)
		
		log.save(ignore_permissions=True)
		frappe.db.commit()

def validate_item_magento_product_id(doc, method):
	# called via hook
	item_name = frappe.db.get_value("Item", {"magento_product_id": doc.get("magento_product_id")}, "name")

	if doc.get("magento_product_id") != 0 and item_name and item_name != doc.name:
		throw(_(f'Magento Product Id {doc.get("magento_product_id")} is already assigned to Item {item_name}.'))

def validate_sales_order_magento_order_id(doc, method):
	# called via hook
	sales_order_name = frappe.db.get_value("Sales Order", {"magento_order_id": doc.get("magento_order_id")}, "name")

	if sales_order_name and sales_order_name != doc.name:
		throw(_(f'Magento Order Id {doc.get("magento_order_id")} is already assigned to Sales Order {sales_order_name}.'))

def validate_delivery_note_magento_shipment_id(doc, method):
	# called via hook
	delivery_note_name = frappe.db.get_value("Delivery Note", {"magento_shipment_id": doc.get("magento_shipment_id")}, "name")

	if delivery_note_name and delivery_note_name != doc.name:
		throw(_(f'Magento Shipment Id {doc.get("magento_shipment_id")} is already assigned to Delivery Note {delivery_note_name}.'))

def validate_sales_invoice_magento_invoice_id(doc, method):
	# called via hook
	sales_invoice_name = frappe.db.get_value("Sales Invoice", {"magento_invoice_id": doc.get("magento_invoice_id")}, "name")

	if sales_invoice_name and sales_invoice_name != doc.name:
		throw(_(f'Magento Invoice Id {doc.get("magento_invoice_id")} is already assigned to Sales Invoice {sales_invoice_name}.'))