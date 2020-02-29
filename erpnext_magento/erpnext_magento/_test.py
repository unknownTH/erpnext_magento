from __future__ import unicode_literals
import frappe

def test():
    test = "hallo test"
    print(test)

def insert_test():
    doc = frappe.get_doc({
        "doctype": "Project",
        "title": "My new project",
        "status": "Open"
    })
    doc.insert()