from __future__ import unicode_literals
import frappe
from frappe import _
import requests.exceptions
from erpnext_magento.erpnext_magento.magento_requests import get_magento_customers, post_request, put_request, get_magento_country_name_by_id, get_magento_country_id_by_name, get_magento_region_id_by_name
from erpnext_magento.erpnext_magento.utils import make_magento_log

def sync_customers():
	magento_customer_list = []
	sync_magento_customers(magento_customer_list)
	frappe.local.form_dict.count_dict["erpnext_customers"] = len(magento_customer_list)
	
	erpnext_customer_list = []
	sync_erpnext_customers(magento_customer_list, erpnext_customer_list)
	frappe.local.form_dict.count_dict["magento_customers"] = len(erpnext_customer_list)

	frappe.db.set_value("Magento Settings", None, "last_sync_datetime", frappe.utils.now())

def sync_magento_customers(magento_customer_list):
	for magento_customer in get_magento_customers():
		import frappe.utils.nestedset
		magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

		customer_dict = {
			"doctype": "Customer",
			"customer_first_name": magento_customer.get("firstname"),
			"customer_middle_name": magento_customer.get("middlename"),
			"customer_last_name": magento_customer.get("lastname"),
			"customer_name" : construct_customer_name(magento_customer),
			"magento_customer_email" : magento_customer.get("email"),
			"magento_customer_id": magento_customer.get("id"),
			"magento_website_id": magento_customer.get("website_id"),
			"sync_with_magento": 1,
			"customer_group": magento_settings.customer_group,
			"territory": frappe.utils.nestedset.get_root_of("Territory"),
			"customer_type": _("Individual")
		}		

		if not frappe.db.get_value("Customer", {"magento_customer_id": magento_customer.get("id")}, "name"):
			create_erpnext_customer(customer_dict, magento_customer, magento_customer_list)
		else:
			update_erpnext_customer(customer_dict, magento_customer, magento_customer_list)

def construct_customer_name(magento_customer):
		if  magento_customer.get("middlename"):
			constructet_customer_name = (magento_customer.get("firstname") + " " \
			+ magento_customer.get("middlename") + " " + magento_customer.get("lastname"))
		else:
			constructet_customer_name = (magento_customer.get("firstname") + " " + magento_customer.get("lastname"))
		
		return constructet_customer_name

def create_erpnext_customer(customer_dict, magento_customer, magento_customer_list):		
	try:
		customer = frappe.get_doc(customer_dict)
		customer.flags.ignore_mandatory = True
		customer.insert()
		
		if customer:
			sync_magento_customer_addresses(customer, magento_customer)
	
		magento_customer_list.append(magento_customer.get("id"))
		frappe.db.commit()
			
	except Exception as e:
		if e.args[0] and e.args[0].startswith("402"):
			raise e
		else:
			make_magento_log(title=e.message, status="Error", method="create_erpnext_customer", message=frappe.get_traceback(),
				request_data=magento_customer, exception=True)

def update_erpnext_customer(customer_dict, magento_customer, magento_customer_list):
	try:
		customer = frappe.get_doc("Customer", frappe.db.get_value("Customer", {"magento_customer_id": magento_customer.get("id")}, "name"))
		customer.update(customer_dict)
		customer.flags.ignore_mandatory = True
		customer.save()

		if customer:
			sync_magento_customer_addresses(customer, magento_customer)
		
		magento_customer_list.append(magento_customer.get("id"))
		frappe.db.commit()
			
	except Exception as e:
		if e.args[0] and e.args[0].startswith("402"):
			raise e
		else:
			make_magento_log(title=e.message, status="Error", method="update_erpnext_customer", message=frappe.get_traceback(),
				request_data=magento_customer, exception=True)

def sync_magento_customer_addresses(customer, magento_customer):
	for i, magento_address in enumerate(magento_customer.get("addresses")):
		magento_address["title"], magento_address["type"] = get_address_title_and_type(customer.customer_name, i)

		fill_empty_address_lines(magento_address)

		address_dict = {
			"doctype": "Address",
			"magento_address_id": magento_address.get("id"),
			"address_title": magento_address["title"],
			"address_type": magento_address["type"],
			"address_line1": magento_address["street"][0],
			"address_line2": magento_address["street"][1],
			"address_line3": magento_address["street"][2],
			"city": magento_address.get("city"),
			"state": magento_address["region"]["region"],
			"pincode": magento_address.get("postcode"),
			"country": get_magento_country_name_by_id(magento_address.get("country_id")),
			"phone": magento_address.get("telephone") or "",
			"is_primary_address": magento_address.get("default_billing"),
			"is_shipping_address": magento_address.get("default_shipping"),
			"magento_customer_id": customer.get("magento_customer_id"),
			"links": [{
				"link_doctype": "Customer",
				"link_name": customer.name
			}]
		}

		if not frappe.db.get_value("Address", {"magento_address_id": magento_address["id"]}, "name"):
			create_erpnext_customer_address(address_dict)
		else:
			update_erpnext_customer_address(address_dict, magento_address)

def fill_empty_address_lines(magento_address):
	if len(magento_address["street"]) < 2:
		magento_address["street"].append("")

	if len(magento_address["street"]) < 3:
		magento_address["street"].append("")

	return magento_address


def create_erpnext_customer_address(address_dict):
	try :
		address = frappe.get_doc(address_dict)
		address.flags.ignore_mandatory = True
		address.insert()
		
	except Exception as e:
		make_magento_log(title=e.message, status="Error", method="create_erpnext_customer_address", message=frappe.get_traceback(),
			request_data=magento_customer, exception=True)

def update_erpnext_customer_address(address_dict, magento_address):
	try:
		address = frappe.get_doc("Address", frappe.db.get_value("Address", {"magento_address_id": magento_address["id"]}, "name"))
		address.update(address_dict)
		address.flags.ignore_mandatory = True
		address.save()

	except Exception as e:
		make_magento_log(title=e.message, status="Error", method="update_erpnext_customer_address", message=frappe.get_traceback(),
			request_data=magento_customer, exception=True)
	
def get_address_title_and_type(customer_name, index):
	address_type = _("Billing")
	address_title = customer_name
	if frappe.db.get_value("Address", "{0}-{1}".format(customer_name.strip(), address_type)):
		address_title = "{0}-{1}".format(customer_name.strip(), index)
		
	return address_title, address_type 
	
def sync_erpnext_customers(magento_customer_list, erpnext_customer_list):
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")
	
	condition = ["sync_with_magento = 1"]
	
	last_sync_condition = ""
	if magento_settings.last_sync_datetime:
		last_sync_condition = "modified >= '{0}' ".format(magento_settings.last_sync_datetime)
		condition.append(last_sync_condition)
	
	customer_query = """select name, customer_first_name, customer_middle_name, customer_last_name,
		magento_customer_id, magento_customer_email,  magento_website_id  from tabCustomer where {0}""".format(" and ".join(condition))

	for customer in frappe.db.sql(customer_query, as_dict=1):
		try:
			customer["magento_customer_id"] = int(customer.get("magento_customer_id"))
			if customer.get("magento_customer_id") not in magento_customer_list:
				update_customer_to_magento(customer)
				erpnext_customer_list.append(customer.get("magento_customer_id"))
			
		except Exception as e:
			make_magento_log(title=e.message, status="Error", method="sync_erpnext_customers", message=frappe.get_traceback(),
				request_data=customer, exception=True)
	
	sync_erpnext_customer_addresses(magento_settings, magento_customer_list, erpnext_customer_list)

def update_customer_to_magento(customer):
	magento_customer_dict = {
		"id": customer.get("magento_customer_id"),
		"firstname": customer.get("customer_first_name"),
		"middlename": customer.get("customer_middle_name"),
		"lastname": customer.get("customer_last_name"),
		"email": customer.get("magento_customer_email"),
		"website_id": customer.get("magento_website_id")
	}
	
	append_address_details(customer, magento_customer_dict)

	try:
		put_request("customers/{0}".format(customer.get("magento_customer_id")), { "customer": magento_customer_dict})
		
	except requests.exceptions.HTTPError as e:
		if e.args[0] and e.args[0].startswith("404"):
			customer = frappe.get_doc("Customer", customer.name)
			customer.magento_customer_id = ""
			customer.sync_with_magento = 0
			customer.flags.ignore_mandatory = True
			customer.save()
		else:
			raise
			
def append_address_details(customer, magento_customer_dict):
	customer_addresses = get_customer_addresses(customer)

	magento_customer_dict['addresses'] = []
	for address in customer_addresses:
		if address.get("magento_address_id"):
			if not address.get("address_line2"):
				address["address_line2"] = ""
			if not address.get("address_line3"):
				address["address_line3"] = ""

			address_dict = {
				"id": address.get("magento_address_id"),
				"street": [address.get("address_line1"), address.get("address_line2"), address.get("address_line3")],
				"region_id": get_magento_region_id_by_name(address.get("state")),
				"country_id": get_magento_country_id_by_name(address.get("country")),
				"telephone": address.get("telephone"),
				"city": address.get("city"),
				"postcode": address.get("pincode"),
				"default_billing": address.get("is_primary_address"),
				"default_shipping": address.get("is_shipping_address")
			}

			magento_customer_dict['addresses'].append(address_dict)

def get_customer_addresses(customer):
	conditions = ["dl.parent = addr.name", "dl.link_doctype = 'Customer'",
		"dl.link_name = '{0}'".format(customer['name'])]
		
	address_query = """select addr.* from tabAddress addr, `tabDynamic Link` dl
		where {0}""".format(' and '.join(conditions))
			
	return frappe.db.sql(address_query, as_dict=1)

def sync_erpnext_customer_addresses(magento_settings, magento_customer_list, erpnext_customer_list):
	condition = ["magento_address_id <> ''"]
	
	last_sync_condition = ""
	if magento_settings.last_sync_datetime:
		last_sync_condition = "modified >= '{0}' ".format(magento_settings.last_sync_datetime)
		condition.append(last_sync_condition)

	address_query = """select magento_customer_id from tabAddress where {0}""".format(" and ".join(condition))

	for address in frappe.db.sql(address_query, as_dict=1):
		customer_query = """select name, customer_first_name, customer_middle_name, customer_last_name,
		magento_customer_id, magento_customer_email,  magento_website_id  from tabCustomer
		where magento_customer_id = {0}""".format(address.get("magento_customer_id"))

		for customer in frappe.db.sql(customer_query, as_dict=1):
			try:
				customer["magento_customer_id"] = int(customer.get("magento_customer_id"))
				if customer.get("magento_customer_id") not in magento_customer_list:
					update_customer_to_magento(customer)
					erpnext_customer_list.append(customer.get("magento_customer_id"))
			
			except Exception as e:
				make_magento_log(title=e.message, status="Error", method="sync_erpnext_customer_addresses", message=frappe.get_traceback(),
					request_data=customer, exception=True)