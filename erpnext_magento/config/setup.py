from __future__ import unicode_literals
from frappe import _

def get_data():
	return [
		{
			"label": _("Integrations"),
			"icon": "icon-star",
			"items": [
				{
					"type": "doctype",
					"name": "Magento Settings",
					"description": _("Connect Magento with ERPNext"),
					"hide_count": True
				}
			]
		}
	]
