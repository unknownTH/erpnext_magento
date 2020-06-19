# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from . import __version__ as app_version

app_name = "erpnext_magento"
app_title = "ERPNext Magento"
app_publisher = "unknownTH"
app_description = "Magento connector for ERPNext"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = ""
app_license = "GNU GPL v3.0"


# fixtures = ["Custom Field", "Custom Script"]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erpnext_magento/css/erpnext_magento.css"
# app_include_js = "/assets/erpnext_magento/js/erpnext_magento.js"

# include js, css files in header of web template
# web_include_css = "/assets/erpnext_magento/css/erpnext_magento.css"
# web_include_js = "/assets/erpnext_magento/js/erpnext_magento.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

doctype_js = {
	"Address": "public/js/doctype_js/address.js",
	"Customer": "public/js/doctype_js/customer.js",
	"Item": "public/js/doctype_js/item.js"
}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "erpnext_magento.install.before_install"
after_install = "erpnext_magento.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "erpnext_magento.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"Item": {
# 		"validate": "erpnext_magento.erpnext_magento.utils.validate_item_magento_sku",
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"hourly": [
		"erpnext_magento.erpnext_magento.api.sync_magento"
	]
}

# Testing
# -------

# before_tests = "erpnext_magento.install.before_tests"

# Overriding Whitelisted Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "erpnext_magento.event.get_events"
# }

