# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

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
		if self.app_type == "Private":
			if not (self.get_password(raise_exception=False) and self.api_key and self.magento_url):
				frappe.msgprint(_("Missing value for Password, API Key or Magento URL"), raise_exception=MagentoSetupError)

		else:
			if not (self.access_token and self.magento_url):
				frappe.msgprint(_("Access token or Magento URL missing"), raise_exception=MagentoSetupError)

	def validate_access(self):
		try:
			get_request('/admin/products.json', {"api_key": self.api_key,
				"password": self.get_password(raise_exception=False), "magento_url": self.magento_url,
				"access_token": self.access_token, "app_type": self.app_type})

		except requests.exceptions.HTTPError:
			# disable magento!
			frappe.db.rollback()
			self.set("enable_magento", 0)
			frappe.db.commit()

			frappe.throw(_("""Invalid Magento app credentials or access token"""), MagentoSetupError)


@frappe.whitelist()
def get_series():
		return {
			"sales_order_series" : frappe.get_meta("Sales Order").get_options("naming_series") or "SO-Magento-",
			"sales_invoice_series" : frappe.get_meta("Sales Invoice").get_options("naming_series")  or "SI-Magento-",
			"delivery_note_series" : frappe.get_meta("Delivery Note").get_options("naming_series")  or "DN-Magento-"
		}
