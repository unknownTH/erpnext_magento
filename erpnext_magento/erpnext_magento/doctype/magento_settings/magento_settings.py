# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import frappe
from frappe import _
import requests.exceptions
from frappe.model.document import Document
from erpnext_magento.erpnext_magento.magento_requests import get_request
from erpnext_magento.erpnext_magento.exceptions import MagentoSetupError

class MagentoSettings(Document):
	def validate(self):
		if self.enable_magento == 1:
			self.validate_access_credentials()
			self.validate_access()

	def validate_access_credentials(self):
		if not (self.api_access_token and self.magento_url):
			frappe.msgprint(_("Magento URL or API access token missing"), raise_exception=MagentoSetupError)

	def validate_access(self):
		try:
			get_request('/products?searchCriteria[pageSize]=1', {"api_access_token": self.api_access_token, "magento_url": self.magento_url})

		except requests.exceptions.HTTPError:
			# disable magento!
			frappe.db.rollback()
			self.set("enable_magento", 0)
			frappe.db.commit()

			frappe.throw(_("""Invalid Magento URL or API access token"""), MagentoSetupError)


@frappe.whitelist()
def get_series():
		return {
			"sales_order_series" : frappe.get_meta("Sales Order").get_options("naming_series") or "SO-Magento-",
			"sales_invoice_series" : frappe.get_meta("Sales Invoice").get_options("naming_series")  or "SI-Magento-",
			"delivery_note_series" : frappe.get_meta("Delivery Note").get_options("naming_series")  or "DN-Magento-"
		}
