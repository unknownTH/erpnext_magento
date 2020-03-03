from __future__ import unicode_literals
import frappe

def test():
    test = "hallo test"
    print(test)

def insert_test():
    doc = frappe.get_doc({
        "doctype": "Project",
        "title": "My new project",
        "name": "My new project",
        "status": "Open"
    })
    doc.insert()

def db_get_value_test():
    print(frappe.db.get_value("Address", {"magento_address_id": 12}, "name"))
    #print(frappe.db.get_value("Customer", {"name": "Jane Updated Doe"}, "customer_first_name"))

def update_doc_item():
    address = frappe.get_doc("Address", frappe.db.get_value("Address", {"magento_address_id": 10}, "name"))

    address.address_line1 = "changed from py test"

    address.flags.ignore_mandatory = True
	address.save()
    frappe.db.commit()