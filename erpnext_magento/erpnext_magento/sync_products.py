from __future__ import unicode_literals
import frappe
from frappe import _
import requests.exceptions
from erpnext_magento.erpnext_magento.exceptions import MagentoError
from erpnext_magento.erpnext_magento.utils import make_magento_log, disable_magento_sync_for_item
from erpnext.stock.utils import get_bin
from frappe.utils import cstr, flt, cint, get_files_path
from erpnext_magento.erpnext_magento.magento_requests import (
	get_magento_category_id_by_name,
	get_magento_category_name_by_id,
	get_magento_items,
	get_magento_item_attribute_details_by_id,
	get_magento_item_attribute_details_by_name,
	get_magento_item_attribute_set_id_by_name,
	get_magento_item_attribute_set_name_by_id,
	get_magento_item_price_by_website,
	get_magento_parent_item_id,
	get_magento_website_id_by_name,
	get_magento_website_name_by_id,
	get_magento_store_code_by_website_id,
	post_request,
	put_request)
import base64, datetime, requests, os

def sync_products():
	sync_item_attributes()

	magento_item_list = []
	sync_magento_items(magento_item_list)
	frappe.local.form_dict.count_dict["erpnext_products"] = len(magento_item_list)

	erpnext_item_list = []
	sync_erpnext_items(erpnext_item_list, magento_item_list)
	frappe.local.form_dict.count_dict["magento_products"] = len(erpnext_item_list)

def sync_item_attributes():
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	for item_variant_attribute in magento_settings.item_variant_attributes:
		magento_item_attribute = get_magento_item_attribute_details_by_name(item_variant_attribute.get("item_variant_attribute"))
		erpnext_item_attribute = frappe.get_doc("Item Attribute", item_variant_attribute.get("item_variant_attribute"))

		if not erpnext_item_attribute.magento_item_attribute_id:
			erpnext_item_attribute.magento_item_attribute_id = magento_item_attribute.get("attribute_id")
			erpnext_item_attribute.magento_item_attribute_code = magento_item_attribute.get("attribute_code")
			erpnext_item_attribute.flags.ignore_mandatory = True
			erpnext_item_attribute.save()
			frappe.db.commit()

		sync_magento_item_attribute_values(erpnext_item_attribute, magento_item_attribute)
		sync_erpnext_item_attribute_values(erpnext_item_attribute, magento_item_attribute)

def sync_magento_item_attribute_values(erpnext_item_attribute, magento_item_attribute):
	for magento_item_attribute_value in magento_item_attribute.get("options"):
		erpnext_item_atribute_value_name_by_id = frappe.db.get_value("Item Attribute Value",
			{"magento_item_attribute_value_id": magento_item_attribute_value.get("value")}, "name")
		erpnext_item_atribute_value_name_by_label = frappe.db.get_value("Item Attribute Value",
			{"attribute_value": magento_item_attribute_value.get("label"), "parent": erpnext_item_attribute.attribute_name}, "name")

		if erpnext_item_atribute_value_name_by_id:
			erpnext_item_attribute_value = frappe.get_doc("Item Attribute Value", erpnext_item_atribute_value_name_by_id)
			erpnext_item_attribute_value.attribute_value = magento_item_attribute_value.get("label")
			erpnext_item_attribute_value.save()

		elif erpnext_item_atribute_value_name_by_label:
			erpnext_item_attribute_value = frappe.get_doc("Item Attribute Value", erpnext_item_atribute_value_name_by_label)
			erpnext_item_attribute_value.magento_item_attribute_value_id = magento_item_attribute_value.get("value")
			erpnext_item_attribute_value.save()

		elif magento_item_attribute_value.get("label") != " ":
			erpnext_item_attribute_value = frappe.get_doc({
				"doctype": "Item Attribute Value",
				"attribute_value": magento_item_attribute_value.get("label"),
				"abbr": magento_item_attribute_value.get("label").upper(),
				"parentfield": "item_attribute_values",
				"parenttype": "Item Attribute",
				"parent": erpnext_item_attribute.name,
				"idx":99,
				"magento_item_attribute_value_id": magento_item_attribute_value.get("value")
			})
			erpnext_item_attribute_value.insert()
		
		frappe.db.commit()	

def sync_erpnext_item_attribute_values(erpnext_item_attribute, magento_item_attribute):
	magento_item_attribute_value_list = []
	
	for erpnext_item_attribute_value in erpnext_item_attribute.item_attribute_values:
		if not erpnext_item_attribute_value.get("magento_item_attribute_value_id"):
			magento_item_attribute_value_dict = {
				"label": erpnext_item_attribute_value.get("attribute_value")
			}

			try:
				request_response = post_request(f'products/attributes/{erpnext_item_attribute.magento_item_attribute_id}/options',
					{"option": magento_item_attribute_value_dict})
				
				erpnext_item_attribute_value.magento_item_attribute_value_id = request_response.strip("id_")
				erpnext_item_attribute_value.save()
				frappe.db.commit()

			except Exception as e:
				make_magento_log(title=f'Cannot sync item attribute value "{erpnext_item_attribute_value.attribute_value}" from item attribute "{erpnext_item_attribute.attribute_name}"',
					status="Error", method="sync_erpnext_item_attribute_values", message=e,	request_data=magento_item_attribute_value_dict, exception=True)				
		
		magento_item_attribute_value_dict = {
			"label": erpnext_item_attribute_value.attribute_value,
			"value": erpnext_item_attribute_value.magento_item_attribute_value_id
		}

		magento_item_attribute_value_list.append(magento_item_attribute_value_dict)

	magento_item_attribute_dict = {
		"attribute_id": erpnext_item_attribute.magento_item_attribute_id, 
		"options": magento_item_attribute_value_list
	}

	put_request(f'products/attributes/{erpnext_item_attribute.magento_item_attribute_id}', {"attribute": magento_item_attribute_dict})

def sync_magento_items(magento_item_list):
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	for magento_item in get_magento_items():
		item_dict = {
			"doctype": "Item",
			"magento_product_id": magento_item.get("id"),
			"sync_with_magento": 1,
			"magento_status": convert_magento_status_to_text(magento_item.get("status")),
			"is_stock_item": 0,
			"item_name": magento_item.get("name"),
			"item_code": magento_item.get("name"),
			"item_group": magento_settings.item_group,
			"stock_uom": _("Nos"),
			"magento_sku": magento_item.get("sku"),
			"magento_attribute_set_name": get_magento_item_attribute_set_name_by_id(magento_item.get("attribute_set_id")),
			"magento_websites": convert_website_ids_list(magento_item.get("extension_attributes").get("website_ids")),
			"magento_categories": convert_catergory_ids_list(magento_item.get("extension_attributes").get("category_links")),
			"default_material_request_type": "Manufacture",
			"magento_description": next((custom_attribute.get("value") for custom_attribute in magento_item.get("custom_attributes") if custom_attribute.get("attribute_code") == "description"), None)
		}

		if not frappe.db.get_value("Item", {"magento_product_id": magento_item.get("id")}, "name"):
			if magento_item.get("type_id") == "configurable":
				item_dict["attributes"] = get_magento_configurable_item_attributes_list(magento_item)
				item_dict["has_variants"] = True

				create_erpnext_item(item_dict, magento_item, magento_item_list)

			elif magento_item.get("type_id") == "simple":
				magento_parent_item_id = get_magento_parent_item_id(magento_item)

				if magento_parent_item_id:
					erpnext_parent_item = frappe.get_doc("Item", frappe.db.get_value("Item", {"magento_product_id": magento_parent_item_id}, "name"))
			
					item_dict["attributes"] = get_magento_variant_item_attributes_list(erpnext_parent_item, magento_item)
					item_dict["variant_of"] = erpnext_parent_item.name

				create_erpnext_item(item_dict, magento_item, magento_item_list)
				
			else:
				raise Exception(f'Magento item type "{magento_item.get("type_id")}" is not compatible with ERPNext.')	

		else:
			if magento_item.get("type_id") == "configurable":
				item_dict["attributes"] = get_magento_configurable_item_attributes_list(magento_item)

			update_erpnext_item(item_dict, magento_item, magento_item_list)

def convert_magento_status_to_text(magento_status):
	if magento_status == 1:
		return "Enabled"
	
	return "Disabled"

def convert_website_ids_list(website_ids_list):
	website_list = []

	if website_ids_list:
		for website_id in website_ids_list:
			website_list.append({"magento_website_name": get_magento_website_name_by_id(website_id)})
		
		return website_list

	return

def convert_catergory_ids_list(category_ids_list):
	category_list = []
	
	if category_ids_list:
		for category in category_ids_list:
			category_list.append({"magento_category_name": get_magento_category_name_by_id(category.get("category_id"))})
		
		return category_list
	
	return

def create_erpnext_item(item_dict, magento_item, magento_item_list):
	try:
		item = frappe.get_doc(item_dict)
		item.flags.ignore_mandatory = True
		item.insert()
		
		sync_magento_item_prices(item.item_code, magento_item)
	
		magento_item_list.append(magento_item.get("id"))
		frappe.db.commit()
			
	except Exception as e:
		if e.args[0] and e.args[0].startswith("402"):
			raise e
		else:
			make_magento_log(title=e.message, status="Error", method="create_erpnext_item", message=frappe.get_traceback(),
				request_data=magento_customer, exception=True)

def sync_magento_item_prices(erpnext_item_code, magento_item):
	for website_id in magento_item.get("extension_attributes").get("website_ids"):
		price_list = get_price_list_by_website_id(website_id)
		item_price_name = frappe.db.get_value("Item Price", {"item_code": erpnext_item_code,
			"price_list": price_list}, "name")
		if not item_price_name:
			frappe.get_doc({
				"doctype": "Item Price",
				"price_list": price_list,
				"item_code": erpnext_item_code,
				"price_list_rate": get_magento_item_price_by_website(magento_item, website_id)
			}).insert()

		else:
			item_price = frappe.get_doc("Item Price", item_price_name)
			item_price.price_list_rate = get_magento_item_price_by_website(magento_item, website_id)
			item_price.save()

def get_price_list_by_website_id(website_id):
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	for price_list in magento_settings.price_lists:
		if price_list.get("magento_website_name") == get_magento_website_name_by_id(website_id):
			return price_list.price_list
	
	raise Exception(f"There is no maching website in ERPNext Magento settings for the Magento website {get_magento_website_name_by_id(website_id)}.")

def get_magento_configurable_item_attributes_list(magento_item):
	attribute_list = []

	for magento_item_attribute in magento_item.get("extension_attributes").get("configurable_product_options"):
		magento_item_attribute_details = get_magento_item_attribute_details_by_id(magento_item_attribute.get("attribute_id"))
		attribute_list.append({"attribute": magento_item_attribute_details.get("default_frontend_label")})

	return attribute_list

def get_magento_variant_item_attributes_list(erpnext_template_item, magento_item):
	attribute_list = []

	for erpnext_template_item_attribute in erpnext_template_item.attributes:
		for magento_item_attribute in magento_item.get("custom_attributes"):
			if magento_item_attribute.get("attribute_code") == frappe.db.get_value("Item Attribute",
				{"attribute_name": erpnext_template_item_attribute.attribute}, "magento_item_attribute_code"):
				magento_item_attribute_value_id = magento_item_attribute.get("value")

		magento_item_attribute_value_dict = {
			"variant_of": erpnext_template_item.name,
			"attribute": erpnext_template_item_attribute.attribute,
			"attribute_value": frappe.db.get_value("Item Attribute Value",
				{"magento_item_attribute_value_id": magento_item_attribute_value_id}, "attribute_value")
		}
		
		attribute_list.append(magento_item_attribute_value_dict)
			

	return attribute_list

def update_erpnext_item(item_dict, magento_item, magento_item_list):
	try:
		item = frappe.get_doc("Item", frappe.db.get_value("Item", {"magento_product_id": magento_item.get("id")}, "name"))

		del item_dict["item_code"]
		del item_dict["item_name"]
		item_dict["magento_attribute_set_name"] = get_magento_item_attribute_set_name_by_id(magento_item.get("attribute_set_id"))
		item_dict["magento_websites"] = convert_website_ids_list(magento_item.get("extension_attributes").get("website_ids"))
		item_dict["magento_categories"] = convert_catergory_ids_list(magento_item.get("extension_attributes").get("category_links"))

		if magento_item.get("type_id") == "configurable":
			item_dict["attributes"] = get_magento_configurable_item_attributes_list(magento_item)	
	
		item.update(item_dict)
		item.flags.ignore_mandatory = True
		item.save()

		if item and magento_item.get("type_id") != "configurable":
			sync_magento_item_prices(item.get("item_code"), magento_item)

		frappe.rename_doc("Item", item.get("name"), magento_item.get("name"))

		magento_item_list.append(magento_item.get("id"))
		frappe.db.commit()
		
			
	except Exception as e:
		if e.args[0] and e.args[0].startswith("402"):
			raise e
		else:
			make_magento_log(title=e.message, status="Error", method="update_erpnext_item", message=frappe.get_traceback(),
				request_data=magento_customer, exception=True)

def sync_erpnext_items(erpnext_item_list, magento_item_list):
	for erpnext_item in get_erpnext_items():
		if erpnext_item.get("magento_product_id") not in magento_item_list:
			if erpnext_item.changed == 'item':
				update_item_to_magento(erpnext_item)
				erpnext_item_list.append(erpnext_item.name)

			elif erpnext_item.changed == 'price' and erpnext_item.name not in erpnext_item_list:
				if not erpnext_item.get("has_variants"):
					update_item_prices_to_magento(erpnext_item)
					erpnext_item_list.append(erpnext_item.name)

def get_erpnext_items():
	erpnext_items = []
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	last_sync_condition = ""
	item_price_condition = ""
	if magento_settings.last_sync_datetime:
		last_sync_condition = f"and modified >= '{magento_settings.last_sync_datetime}' "
		item_price_condition = f"and ip.modified >= '{magento_settings.last_sync_datetime}' "

	item_from_master_sql = f"""SELECT 'item' as changed, name, item_code, magento_sku, item_name, description,
		magento_description, has_variants, variant_of, stock_uom, CAST(magento_product_id AS INT) AS magento_product_id, magento_attribute_set_name,
		magento_status FROM tabItem	WHERE sync_with_magento=1 and (disabled is null or disabled = 0) {last_sync_condition}
		order by has_variants ASC"""

	erpnext_items.extend(frappe.db.sql(item_from_master_sql, as_dict=1))

	price_lists_sql = """SELECT price_list FROM `tabMagento Price List`"""

	item_from_item_price_sql = f"""SELECT 'price' as changed, i.name, i.item_code, i.magento_sku, i.item_name, i.item_group, i.description,
		i.magento_description, i.has_variants, i.variant_of, CAST(i.magento_product_id AS INT) AS magento_product_id, i.magento_attribute_set_name,
		magento_status FROM tabItem i, `tabItem Price` ip WHERE price_list in ({price_lists_sql}) and i.name = ip.item_code
		AND sync_with_magento=1 and (disabled is null OR disabled = 0) {item_price_condition}"""

	updated_price_item_list = frappe.db.sql(item_from_item_price_sql, as_dict=1)

	return erpnext_items + updated_price_item_list

def update_item_to_magento(erpnext_item):
	magento_item_dict = {
		"id": erpnext_item.get("magento_product_id") or "",
		"sku": erpnext_item.get("magento_sku") or erpnext_item.get("item_name").replace(" ", "").replace(":", "-").replace("/", "-"),
		"name": erpnext_item.get("item_name"),
		"attribute_set_id": get_magento_item_attribute_set_id_by_name(erpnext_item.get("magento_attribute_set_name")),
		"status": convert_magento_status_to_boolean(erpnext_item.get("magento_status")),
		"weight": 1,
		"extension_attributes": {
			"website_ids": get_magento_website_ids_list(erpnext_item),
			"category_links": get_magento_category_ids_list(erpnext_item)
		},
		"custom_attributes": [
			{
    			"attribute_code": "description",
        		"value": erpnext_item.get("magento_description") or ""
        	}
		]
	}

	if erpnext_item.get("has_variants"): 
		magento_item_dict.update({
			"type_id": "configurable",
			"price": 0})
		magento_item_dict["extension_attributes"].update({"configurable_product_options": get_magento_configurable_product_options(erpnext_item)})
		magento_item_dict["extension_attributes"].update({"configurable_product_links": get_magento_configurable_product_variant_links(erpnext_item)})	
	
	elif erpnext_item.get("variant_of"):
		magento_item_dict.update({
			"type_id": "simple",
			"visibility": 1,
			"price": get_magento_default_item_price(erpnext_item)
		})
		magento_item_dict["custom_attributes"].extend(get_magento_variant_product_attributes(erpnext_item))
		
	else:
		magento_item_dict.update({
			"type_id": "simple",
			"price": get_magento_default_item_price(erpnext_item)
		})

	try:
		if not erpnext_item.get("magento_product_id"):
			del magento_item_dict["id"]

			request_response = post_request("rest/all/V1/products", {"product": magento_item_dict})

			save_new_magento_properties_to_erpnext(erpnext_item.get("name"), request_response)
			erpnext_item["magento_sku"] = magento_item_dict.get("sku")

			if not erpnext_item.get("has_variants"):
				update_item_prices_to_magento(erpnext_item)

		else:
			post_request("rest/all/V1/products", {"product": magento_item_dict})

			erpnext_item["magento_sku"] = magento_item_dict.get("sku")

			if not erpnext_item.get("has_variants"):
				update_item_prices_to_magento(erpnext_item)

	except Exception as e:
		if e.args[0] and e.args[0].startswith("404"):
			erpnext_item.magento_item_id = ""
			erpnext_item.sync_with_magento = 0
			erpnext_item.flags.ignore_mandatory = True
			erpnext_item.save()

		exception_title = f'Failed to sync item "{erpnext_item.get("item_name")}".'
		make_magento_log(title=exception_title, status="Error", method="sync_magento_items", message=frappe.get_traceback(),
						request_data=erpnext_item, exception=True)
		raise

def convert_magento_status_to_boolean(magento_status):
	if magento_status == "Enabled":
		return 1
	
	return 0

def get_magento_default_item_price(erpnext_item):
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	try:
		return frappe.db.get_value("Item Price", {"item_code": erpnext_item.get("item_code"),
			"price_list": magento_settings.default_price_list}, "price_list_rate")

	except Exception as e:
		error_message = f'Item "{erpnext_item.get("item_name")}" has no price in Magento Settings default price list "{magento_settings.default_price_list}".'
		make_magento_log(title="Missing Price in Default Price List", status="Error", method="sync_magento_items", message=frappe.get_traceback(),
			request_data=erpnext_item, exception=True)	

def get_magento_website_ids_list(erpnext_item):
	magento_website_ids_list = []

	magento_website_name_sql = f"""select magento_website_name from `tabMagento Websites`
		where parent = '{erpnext_item.name}' order by magento_website_name DESC"""

	magento_websites = frappe.db.sql(magento_website_name_sql, as_dict=1)

	for magento_website in magento_websites: 
		magento_website_ids_list.append(get_magento_website_id_by_name(magento_website.get("magento_website_name")))

	return magento_website_ids_list

def get_magento_category_ids_list(erpnext_item):
	magento_category_ids_list = []

	magento_category_name_sql = f"""select magento_category_name from `tabMagento Categories`
		where parent = '{erpnext_item.name}' order by magento_category_name DESC"""

	magento_categories = frappe.db.sql(magento_category_name_sql, as_dict=1)

	for magento_category in magento_categories:
		magento_category_ids_list.append({"position": 0,
			"category_id": get_magento_category_id_by_name(magento_category.get("magento_category_name"))})

	return magento_category_ids_list

def get_magento_configurable_product_options(erpnext_item):
	configurable_product_options_list = []

	erpnext_item_attributes = frappe.db.get_all("Item Variant Attribute", filters={"parent": erpnext_item.get("name")},
		fields=["attribute"])
 
	for attribute in erpnext_item_attributes:
		magento_attribute_details = get_magento_item_attribute_details_by_name(attribute.get("attribute"))

		configurable_product_option_dict =	{
        	"attribute_id": magento_attribute_details.get("attribute_id"),
        	"label": magento_attribute_details.get("default_frontend_label"),
        	"values": get_magento_configurable_product_options_values(erpnext_item, magento_attribute_details)
		}

		configurable_product_options_list.append(configurable_product_option_dict)
		
	return configurable_product_options_list

def get_magento_configurable_product_options_values(erpnext_item, magento_attribute_details):
	values_list = []
	erpnext_item_attribute_values = frappe.db.get_all("Item Variant Attribute", filters={"variant_of": erpnext_item.get("name")},
		fields=["attribute", "attribute_value"])

	for erpnext_item_attribute_value in erpnext_item_attribute_values:
		values_list.append({"value_index": frappe.db.get_value("Item Attribute Value",
			{"attribute_value": erpnext_item_attribute_value.get("attribute_value")}, "magento_item_attribute_value_id")})			

	return values_list

def get_magento_configurable_product_variant_links(erpnext_item):
	variant_links_list = []

	for variant_link in frappe.db.get_list("Item", filters={"variant_of": erpnext_item.name}, fields=["magento_product_id"]):
		variant_links_list.append(variant_link.get("magento_product_id"))

	return variant_links_list

def get_magento_variant_product_attributes(erpnext_item):
	attribute_list = []
	
	erpnext_item_variant_attributes = frappe.get_all("Item Variant Attribute", filters={"parent": erpnext_item.get("item_code")},
		fields=["attribute", "attribute_value"])
	
	for erpnext_item_variant_attribute in erpnext_item_variant_attributes:
		attribute_code = frappe.db.get_value("Item Attribute", {"attribute_name": erpnext_item_variant_attribute.get("attribute")},
			"magento_item_attribute_code")
		value = frappe.db.get_value("Item Attribute Value",	{"parent": erpnext_item_variant_attribute.get("attribute"),
			"attribute_value": erpnext_item_variant_attribute.get("attribute_value")}, "magento_item_attribute_value_id")
		
		attribute_list.append({"attribute_code": attribute_code, "value": value})

	return attribute_list

def save_new_magento_properties_to_erpnext(item_name, request_response):
	erpnext_item = frappe.get_doc("Item", item_name)

	erpnext_item.magento_product_id = request_response.get("id")
	erpnext_item.magento_sku = request_response.get("sku")
	erpnext_item.save()
	frappe.db.commit()

def update_item_prices_to_magento(erpnext_item):
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	erpnext_item_magento_websites_list = frappe.get_all("Magento Websites", filters={"parent": erpnext_item.get("item_code")},
		fields=["magento_website_name"])

	for erpnext_item_magento_website in erpnext_item_magento_websites_list:
		erpnext_price_list = get_price_list_for_magento_website(erpnext_item_magento_website.get("magento_website_name"))
		store_code = get_magento_store_code_by_website_id(get_magento_website_id_by_name(erpnext_item_magento_website.get("magento_website_name")))
		price = frappe.db.get_value("Item Price", {"item_code": erpnext_item.get("item_code"),
			"price_list": erpnext_price_list}, "price_list_rate")

		try:	
			if price:
				put_request(f'rest/{store_code}/V1/products/{erpnext_item.get("magento_sku")}', {"product": {"price": price}}) 
			
			else:
				raise Exception(f'Item "{erpnext_item.get("item_name")}" has no price in price list \
	"{erpnext_price_list}" which is associated with Magento Website "{erpnext_item_magento_website.get("magento_website_name")}" in Magento Settings.')

		except Exception as e:
			make_magento_log(title=e.message, status="Error", method="sync_magento_items", message=frappe.get_traceback(),
							request_data=erpnext_item, exception=True)

def get_price_list_for_magento_website(magento_website_name):
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	for website in magento_settings.price_lists:
		if website.get("magento_website_name") == magento_website_name:
			return website.get("price_list")
	
	raise Exception(f'Website "{magento_website_name}" is not asociated with a price list in Magento settings.')