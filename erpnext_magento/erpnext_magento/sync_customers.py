from __future__ import unicode_literals
import frappe
from frappe import _
import requests.exceptions
from erpnext_magento.erpnext_magento.magento_requests import get_magento_customers, post_request, put_request, get_country_by_id
from erpnext_magento.erpnext_magento.utils import make_magento_log

def sync_customers():
	magento_customer_list = []
	sync_magento_customers(magento_customer_list)
	frappe.local.form_dict.count_dict["customers"] = len(magento_customer_list)
	
	# sync_erpnext_customers(magento_customer_list)

def sync_magento_customers(magento_customer_list):
	for magento_customer in get_magento_customers():
		if not frappe.db.get_value("Customer", {"magento_customer_id": magento_customer.get('id')}, "name"):
			create_customer(magento_customer, magento_customer_list)

def create_customer(magento_customer, magento_customer_list):
	import frappe.utils.nestedset
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")
	
	cust_name = (magento_customer.get("firstname") + " " + (magento_customer.get("lastname") \
		and  magento_customer.get("lastname") or "")) if magento_customer.get("firstname")\
		else magento_customer.get("email")
		
	try:
		customer = frappe.get_doc({
			"doctype": "Customer",
			"name": magento_customer.get("id"),
			"customer_name" : cust_name,
			"magento_customer_id": magento_customer.get("id"),
			"sync_with_magento": 1,
			"customer_group": magento_settings.customer_group,
			"territory": frappe.utils.nestedset.get_root_of("Territory"),
			"customer_type": _("Individual")
		})
		customer.flags.ignore_mandatory = True
		customer.insert()
		
		if customer:
			create_customer_address(customer, magento_customer)
	
		magento_customer_list.append(magento_customer.get("id"))
		frappe.db.commit()
			
	except Exception as e:
		if e.args[0] and e.args[0].startswith("402"):
			raise e
		else:
			make_magento_log(title=e.message, status="Error", method="create_customer", message=frappe.get_traceback(),
				request_data=magento_customer, exception=True)
		
def create_customer_address(customer, magento_customer):
	for i, address in enumerate(magento_customer.get("addresses")):
		address_title, address_type = get_address_title_and_type(customer.customer_name, i)

		address_line_counter = len(address["street"])
		if address_line_counter == 1:
			adress_line1 = address["street"][0]
			adress_line2 = ""
			adress_line3 = ""
		if address_line_counter == 2:
			adress_line1 = address["street"][0]
			adress_line2 = address["street"][1]
			adress_line3 = ""
		if address_line_counter == 3:
			adress_line1 = address["street"][0]
			adress_line2 = address["street"][1]
			adress_line3 = address["street"][2]

		try :
			frappe.get_doc({
				"doctype": "Address",
				"magento_address_id": address.get("id"),
				"address_title": address_title,
				"address_type": address_type,
				"address_line1": adress_line1,
				"address_line2": adress_line2,
				"address_line3": adress_line3,
				"city": address.get("city"),
				"state": address["region"]["region"],
				"pincode": address.get("postcode"),
				"country": get_country_by_id(address.get("country_id")),
				"phone": address.get("telephone") or "",
				"email_id": magento_customer.get("email"),
				"links": [{
					"link_doctype": "Customer",
					"link_name": customer.name
				}]
			}).insert()
			
		except Exception as e:
			make_magento_log(title=e.message, status="Error", method="create_customer_address", message=frappe.get_traceback(),
				request_data=magento_customer, exception=True)
		
def get_address_title_and_type(customer_name, index):
	address_type = _("Billing")
	address_title = customer_name
	if frappe.db.get_value("Address", "{0}-{1}".format(customer_name.strip(), address_type)):
		address_title = "{0}-{1}".format(customer_name.strip(), index)
		
	return address_title, address_type 
	
def sync_erpnext_customers(magento_customer_list):
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")
	
	condition = ["sync_with_magento = 1"]
	
	last_sync_condition = ""
	if magento_settings.last_sync_datetime:
		last_sync_condition = "modified >= '{0}' ".format(magento_settings.last_sync_datetime)
		condition.append(last_sync_condition)
	
	customer_query = """select name, customer_name, magento_customer_id from tabCustomer 
		where {0}""".format(" and ".join(condition))
		
	for customer in frappe.db.sql(customer_query, as_dict=1):
		try:
			if not customer.magento_customer_id:
				create_customer_to_magento(customer)
			
			else:
				if customer.magento_customer_id not in magento_customer_list:
					update_customer_to_magento(customer, magento_settings.last_sync_datetime)
			
			frappe.local.form_dict.count_dict["customers"] += 1
			frappe.db.commit()
		except Exception as e:
			make_magento_log(title=e.message, status="Error", method="sync_erpnext_customers", message=frappe.get_traceback(),
				request_data=customer, exception=True)

def create_customer_to_magento(customer):
	magento_customer = {
		"firstname": customer['customer_name'],
	}
	
	magento_customer = post_request("customers", { "customer": magento_customer})
	
	customer = frappe.get_doc("Customer", customer['name'])
	customer.magento_customer_id = magento_customer['customer'].get("id")
	
	customer.flags.ignore_mandatory = True
	customer.save()
	
	addresses = get_customer_addresses(customer.as_dict())
	for address in addresses:
		sync_customer_address(customer, address)

def sync_customer_address(customer, address):
	address_name = address.pop("name")

	magento_address = post_request("/admin/customers/{0}/addresses.json".format(customer.magento_customer_id),
	{"address": address})
		
	address = frappe.get_doc("Address", address_name)
	address.magento_address_id = magento_address['customer_address'].get("id")
	address.save()
	
def update_customer_to_magento(customer, last_sync_datetime):
	magento_customer = {
		"firstname": customer['customer_name'],
		"lastname": ""
	}
	
	try:
		put_request("/admin/customers/{0}.json".format(customer.magento_customer_id),\
			{ "customer": magento_customer})
		update_address_details(customer, last_sync_datetime)
		
	except requests.exceptions.HTTPError as e:
		if e.args[0] and e.args[0].startswith("404"):
			customer = frappe.get_doc("Customer", customer.name)
			customer.magento_customer_id = ""
			customer.sync_with_magento = 0
			customer.flags.ignore_mandatory = True
			customer.save()
		else:
			raise
			
def update_address_details(customer, last_sync_datetime):
	customer_addresses = get_customer_addresses(customer, last_sync_datetime)
	for address in customer_addresses:
		if address.magento_address_id:
			url = "/admin/customers/{0}/addresses/{1}.json".format(customer.magento_customer_id,\
			address.magento_address_id)
			
			address["id"] = address["magento_address_id"]
			
			del address["magento_address_id"]
			
			put_request(url, { "address": address})
			
		else:
			sync_customer_address(customer, address)
			
def get_customer_addresses(customer, last_sync_datetime=None):
	conditions = ["dl.parent = addr.name", "dl.link_doctype = 'Customer'",
		"dl.link_name = '{0}'".format(customer['name'])]
	
	if last_sync_datetime:
		last_sync_condition = "addr.modified >= '{0}'".format(last_sync_datetime)
		conditions.append(last_sync_condition)
	
	address_query = """select addr.name, addr.address_line1 as address1, addr.address_line2 as address2,
		addr.city as city, addr.state as province, addr.country as country, addr.pincode as zip,
		addr.magento_address_id from tabAddress addr, `tabDynamic Link` dl
		where {0}""".format(' and '.join(conditions))
			
	return frappe.db.sql(address_query, as_dict=1)
