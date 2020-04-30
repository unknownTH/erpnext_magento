from __future__ import unicode_literals
import frappe
from frappe import _

def after_install():
    add_fields_to_copy_from_template_to_variant_item()

def add_fields_to_copy_from_template_to_variant_item():
    fields_list = ["sync_with_magento", "magento_attribute_set_name", "magento_websites", "magento_categories", "magento_description"]

    for field in fields_list:
        if not frappe.db.get_value("Variant Field", {"field_name": field}, "name"):
            variant_field = frappe.get_doc({
                "doctype": "Variant Field",
                "parent": "Item Variant Settings",
                "parentfield": "fields",
                "parenttype": "Item Variant Settings",
                "idx":99,
                "field_name": field
            })
            variant_field.insert()
            frappe.db.commit()

