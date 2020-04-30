# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import frappe
from frappe import _
from erpnext_magento.erpnext_magento.exceptions import MagentoError
from erpnext_magento.erpnext_magento.sync_orders import sync_orders
from erpnext_magento.erpnext_magento.sync_customers import sync_customers
from erpnext_magento.erpnext_magento.sync_products import sync_products
from erpnext_magento.erpnext_magento.utils import disable_magento_sync_on_exception, make_magento_log
from frappe.utils.background_jobs import enqueue

@frappe.whitelist()
def sync_magento():
	"Enqueue longjob for syncing magento"
	enqueue("erpnext_magento.erpnext_magento.api.sync_magento_resources", queue='long')
	frappe.msgprint(_("Queued for syncing. It may take a few minutes to an hour if this is your first sync."))

@frappe.whitelist()
def sync_magento_resources():
	magento_settings = frappe.get_doc("Magento Settings")

	make_magento_log(title="Sync Job Queued", status="Queued", method=frappe.local.form_dict.cmd, message="Sync Job Queued")
	
	if magento_settings.enable_magento:
		try :
			validate_magento_settings(magento_settings)
			frappe.local.form_dict.count_dict = {}
			sync_products()
			sync_customers()
			sync_orders()
			frappe.db.set_value("Magento Settings", None, "last_sync_datetime", frappe.utils.now())

			make_magento_log(title="Sync Completed", status="Success", method=frappe.local.form_dict.cmd, 
				# message= "Updated: {customers} customer(s), {products} item(s), {orders} order(s)".format(**frappe.local.form_dict.count_dict))
				message= "Updated: \n {erpnext_customers} ERPNext customer(s), {magento_customers} Magento customer(s) \n \
{erpnext_products} ERPNext products(s), {magento_products} Magento products(s) \n \
{erpnext_orders} ERPNext order(s)".format(**frappe.local.form_dict.count_dict))

		except Exception as e:
			make_magento_log(title="sync has terminated", status="Error", method="sync_magento_resources",
				message=frappe.get_traceback(), exception=True)
					
	elif frappe.local.form_dict.cmd == "erpnext_magento.api.sync_magento":
		make_magento_log(
			title="Magento connector is disabled",
			status="Error",
			method="sync_magento_resources",
			message=_("""Magento connector is not enabled. Click on 'Connect to Magento' to connect ERPNext and your Magento store."""),
			exception=True)

def validate_magento_settings(magento_settings):
	"""
		This will validate mandatory fields and access token or app credentials 
		by calling validate() of magento settings.
	"""
	try:
		magento_settings.save()
	except MagentoError:
		disable_magento_sync_on_exception()

@frappe.whitelist()
def get_log_status():
	log = frappe.db.sql("""select name, status from `tabMagento Log` 
		order by modified desc limit 1""", as_dict=1)
	if log:
		if log[0].status=="Queued":
			message = _("Last sync request is queued")
			alert_class = "alert-warning"
		elif log[0].status=="Error":
			message = _("Last sync request was failed, check <a href='../desk#Form/Magento Log/{0}'> here</a>"
				.format(log[0].name))
			alert_class = "alert-danger"
		else:
			message = _("Last sync request was successful")
			alert_class = "alert-success"
			
		return {
			"text": message,
			"alert_class": alert_class
		}
		