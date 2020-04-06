from __future__ import unicode_literals
import frappe
from frappe import _
import requests.exceptions
from erpnext_magento.erpnext_magento.exceptions import MagentoError
from erpnext_magento.erpnext_magento.utils import make_magento_log, disable_magento_sync_for_item
from erpnext.stock.utils import get_bin
from frappe.utils import cstr, flt, cint, get_files_path
from erpnext_magento.erpnext_magento.magento_requests import (get_magento_items, get_magento_item_attribute_details_by_code,
	get_magento_item_attribute_details_by_name, get_magento_item_atrribute_values, get_magento_item_price_by_website,
	get_magento_parent_item_id,	get_magento_website_name_by_id, post_request, put_request)
import base64, datetime, requests, os

def sync_products():
	magento_item_list = []
	sync_magento_items(magento_item_list)
	frappe.local.form_dict.count_dict["erpnext_products"] = len(magento_item_list)

	erpnext_item_list = []
	sync_erpnext_items(erpnext_item_list)
	frappe.local.form_dict.count_dict["magento_products"] = len(erpnext_item_list)

def sync_magento_items(magento_item_list):
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	for magento_item in get_magento_items():
		item_dict = {
			"doctype": "Item",
			"magento_product_id": magento_item.get("id"),
			"magento_variant_id": magento_item.get("variant_id"),
			"sync_with_magento": 1,
			"is_stock_item": 0,
			"item_name": magento_item.get("name"),
			"item_code": magento_item.get("name"),
			"item_group": magento_settings.item_group,
			"stock_uom": _("Nos"),
			"stock_keeping_unit": magento_item.get("sku"),
			"default_warehouse": magento_settings.warehouse,
			"default_material_request_type": "Manufacture"
		}

		if not frappe.db.get_value("Item", {"magento_product_id": magento_item.get("id")}, "name"):
			if magento_item.get("type_id") == "configurable":
				item_dict["attributes"] = sync_magento_item_attributes(magento_item)
				item_dict["has_variants"] = True
		
			elif magento_item.get("type_id") == "virtual":
				erpnext_parent_item = frappe.get_doc("Item", frappe.db.get_value("Item",
					{"magento_product_id": get_magento_parent_item_id(magento_item)}, "name"))
		
				item_dict["attributes"] = sync_magento_variant_item_attributes(erpnext_parent_item, magento_item)
				item_dict["variant_of"] = erpnext_parent_item.name
				
			elif magento_item.get("type_id") != "simple":
				raise Exception('Magento item type "{0}" is not compatible with ERPNext.'.format(magento_item.get("type_id")))

			create_erpnext_item(item_dict, magento_item, magento_item_list)

		else:
			if magento_item.get("type_id") == "configurable":
				item_dict["attributes"] = sync_magento_item_attributes(magento_item)

			update_erpnext_item(item_dict, magento_item, magento_item_list)
		
def create_erpnext_item(item_dict, magento_item, magento_item_list):
	try:
		item = frappe.get_doc(item_dict)
		item.flags.ignore_mandatory = True
		item.insert()
		
		if item and magento_item.get("type_id") != "configurable":
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
		item_price_name = frappe.db.get_value("Item Price", {"item_code": erpnext_item_code,
			"price_list": get_price_list_by_website_id(website_id)}, "name")
		if not item_price_name:
			frappe.get_doc({
				"doctype": "Item Price",
				"price_list": get_price_list_by_website_id(website_id),
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
	
	raise Exception("There is no maching website in ERPNext Magento settings for the Magento website {0}.".\
		format(get_magento_website_name_by_id(website_id)))

def sync_magento_item_attributes(magento_item):
	attribute_list = []

	for magento_item_attribute in magento_item.get("extension_attributes").get("configurable_product_options"):
		if not frappe.db.get_value("Item Attribute", magento_item_attribute.get("label"), "name"):
			create_erpnext_item_attribute(magento_item_attribute)

		else:
			update_erpnext_item_attribute(magento_item_attribute)
		
		attribute_list.append({"attribute": magento_item_attribute.get("label")})

	return attribute_list

def create_erpnext_item_attribute(magento_item_attribute):
	erpnext_item_attribute = frappe.get_doc({
		"doctype": "Item Attribute",
		"attribute_name": magento_item_attribute.get("label")
	})

	erpnext_item_attribute.flags.ignore_mandatory = True
	erpnext_item_attribute.insert()

	for magento_item_attribute_value in get_magento_item_atrribute_values(magento_item_attribute.get("attribute_id")):
		if not magento_item_attribute_value.get("label") == " ":
			erpnext_item_attribute_value = frappe.get_doc({
				"doctype": "Item Attribute Value",
				"attribute_value": magento_item_attribute_value.get("label"),
				"abbr": magento_item_attribute_value.get("label").upper(),
				"parentfield": "item_attribute_values",
				"parenttype": "Item Attribute",
				"parent": magento_item_attribute.get("label"),
				"idx":99
			})

			erpnext_item_attribute_value.flags.ignore_mandatory = True
			erpnext_item_attribute_value.insert()

def update_erpnext_item_attribute(magento_item_attribute):
	erpnext_item_attribute = frappe.get_doc("Item Attribute", magento_item_attribute.get("label"))
	if not erpnext_item_attribute.numeric_values:
		for magento_item_attribute_value in get_magento_item_atrribute_values(magento_item_attribute.get("attribute_id")):
			if not magento_item_attribute_value.get("label") == " " \
			and not is_erpnext_item_attribute_value_exists(erpnext_item_attribute, magento_item_attribute_value):
				erpnext_item_attribute_value = frappe.get_doc({
					"doctype": "Item Attribute Value",
					"attribute_value": magento_item_attribute_value.get("label"),
					"abbr": magento_item_attribute_value.get("label").upper(),
					"parentfield": "item_attribute_values",
					"parenttype": "Item Attribute",
					"parent": erpnext_item_attribute.name,
					"idx":99
				})

				erpnext_item_attribute_value.flags.ignore_mandatory = True
				erpnext_item_attribute_value.insert()

	else:
		# under construction
		attribute.append({
			"attribute": magento_attr.get("label"),
			"from_range": item_attr.get("from_range"),
			"to_range": item_attr.get("to_range"),
			"increment": item_attr.get("increment"),
			"numeric_values": item_attr.get("numeric_values")
		})

def is_erpnext_item_attribute_value_exists(erpnext_item_attribute, magento_item_attribute_value):
	for erpnext_item_attribute_value in erpnext_item_attribute.item_attribute_values:
		if erpnext_item_attribute_value.get("attribute_value") == magento_item_attribute_value.get("label"):
			return True
	
	return False

def sync_magento_variant_item_attributes(erpnext_parent_item, magento_item):
	attribute_list = []

	for erpnext_parent_item_attribute in erpnext_parent_item.attributes:
		attribute_list.append({"attribute": erpnext_parent_item_attribute.attribute,
			"attribute_value": get_magento_variant_item_attribute_value(erpnext_parent_item_attribute.attribute, magento_item)})

	return attribute_list

def get_magento_variant_item_attribute_value(erpnext_parent_item_attribute_name, magento_item):
	erpnext_parent_item_attribute_code = get_magento_item_attribute_details_by_name(erpnext_parent_item_attribute_name).get("attribute_code")

	for magento_item_attribute in magento_item.get("custom_attributes"):
		if  magento_item_attribute.get("attribute_code") == erpnext_parent_item_attribute_code:
			magento_item_attribute_details = get_magento_item_attribute_details_by_code(magento_item_attribute.get("attribute_code"))

			for option in magento_item_attribute_details.get("options"):
				if option.get("value") == magento_item_attribute.get("value"):
					return option.get("label")

def update_erpnext_item(item_dict, magento_item, magento_item_list):
	try:
		item = frappe.get_doc("Item", frappe.db.get_value("Item", {"magento_product_id": magento_item.get("id")}, "name"))

		del item_dict["item_code"]
		
		item.update(item_dict)
		item.flags.ignore_mandatory = True
		item.save()

		if item and magento_item.get("type_id") != "configurable":
			sync_magento_item_prices(item.item_code, magento_item)
		
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
		if erpnext_item.magento_product_id not in magento_item_list:
			try:
				sync_item_with_magento(erpnext_item)
				erpnext_item_list.append(erpnext_item.name)

			except MagentoError as e:
				make_magento_log(title=e.message, status="Error", method="sync_magento_items", message=frappe.get_traceback(),
					request_data=item, exception=True)
			except Exception as e:
				make_magento_log(title=e.message, status="Error", method="sync_magento_items", message=frappe.get_traceback(),
					request_data=item, exception=True)	

def get_erpnext_items():
	erpnext_items = []
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")

	last_sync_condition = ""
	item_price_condition = ""
	if magento_settings.last_sync_datetime:
		last_sync_condition = "and modified >= '{0}' ".format(magento_settings.last_sync_datetime)
		item_price_condition = "and ip.modified >= '{0}' ".format(magento_settings.last_sync_datetime)

	item_from_master_sql = """SELECT name, item_code, item_name, description, magento_description,
		has_variants, variant_of, stock_uom, image, magento_product_id, magento_variant_id,
		sync_qty_with_magento FROM tabItem WHERE sync_with_magento=1 and (variant_of is null or variant_of = '')
		and (disabled is null or disabled = 0) {0} ORDER BY has_variants DESC""".format(last_sync_condition)

	erpnext_items.extend(frappe.db.sql(item_from_master_sql, as_dict=1))

	template_items = [item.name for item in erpnext_items if item.has_variants]

	if len(template_items) > 0:
		item_price_condition += ' and i.variant_of not in (%s)'%(' ,'.join(["'%s'"]*len(template_items)))%tuple(template_items)

	price_lists_sql = """select price_list from `tabMagento Price Lists`"""

	item_from_item_price_sql = """SELECT i.name, i.item_code, i.item_name, i.item_group, i.description,
		i.magento_description, i.has_variants, i.variant_of, i.stock_uom, i.magento_product_id,
		i.magento_variant_id, i.sync_qty_with_magento FROM `tabItem` i, `tabItem Price` ip
		WHERE price_list in ({0}) and i.name = ip.item_code	and sync_with_magento=1
		and (disabled is null or disabled = 0) {1}""".format(price_lists_sql, item_price_condition)

	updated_price_item_list = frappe.db.sql(item_from_item_price_sql, as_dict=1)

	# to avoid item duplication
	return [frappe._dict(tupleized) for tupleized in set(tuple(item.items())
		for item in erpnext_items + updated_price_item_list)]






# ----------------------------------------------------------------------------------------------------------------------------------------------- #
# ----------------------------------------------------------------------------------------------------------------------------------------------- #
# ----------------------------------------------------------------------------------------------------------------------------------------------- #
# ----------------------------------------------------------------------------------------------------------------------------------------------- #





def sync_item_with_magento(item, price_list, warehouse):
	variant_item_name_list = []

	item_data = { "product":
		{
			"title": item.get("item_name"),
			"body_html": item.get("magento_description") or item.get("description"),
			"product_type": item.get("item_group"),
			"vendor": item.get("default_supplier"),
			"published_scope": "global",
			"published_status": "published",
			"published_at": datetime.datetime.now().isoformat()
		}
	}

	if item.get("has_variants") or item.get("variant_of"):

		if item.get("variant_of"):
			item = frappe.get_doc("Item", item.get("variant_of"))

		variant_list, options, variant_item_name = get_variant_attributes(item, price_list, warehouse)

		item_data["product"]["title"] = item.get("item_name")
		item_data["product"]["body_html"] = item.get("magento_description") or item.get("description")
		item_data["product"]["variants"] = variant_list
		item_data["product"]["options"] = options

		variant_item_name_list.extend(variant_item_name)

	else:
		item_data["product"]["variants"] = [get_price_and_stock_details(item, warehouse, price_list)]

	erp_item = frappe.get_doc("Item", item.get("name"))
	erp_item.flags.ignore_mandatory = True
	
	if not item.get("magento_product_id"):
		create_new_item_to_magento(item, item_data, erp_item, variant_item_name_list)

	else:
		item_data["product"]["id"] = item.get("magento_product_id")
		try:
			put_request("/admin/products/{}.json".format(item.get("magento_product_id")), item_data)

		except requests.exceptions.HTTPError as e:
			if e.args[0] and e.args[0].startswith("404"):
				if frappe.db.get_value("Magento Settings", "Magento Settings", "if_not_exists_create_item_to_magento"):
					item_data["product"]["id"] = ''
					create_new_item_to_magento(item, item_data, erp_item, variant_item_name_list)
				else:
					disable_magento_sync_for_item(erp_item)
			else:
				raise e

	sync_item_image(erp_item)
	frappe.db.commit()

def create_new_item_to_magento(item, item_data, erp_item, variant_item_name_list):
	new_item = post_request("/admin/products.json", item_data)
	erp_item.magento_product_id = new_item['product'].get("id")

	if not item.get("has_variants"):
		erp_item.magento_variant_id = new_item['product']["variants"][0].get("id")

	erp_item.save()
	update_variant_item(new_item, variant_item_name_list)

def sync_item_image(item):
	image_info = {
        "image": {}
	}

	if item.image:
		img_details = frappe.db.get_value("File", {"file_url": item.image}, ["file_name", "content_hash"])

		if img_details and img_details[0] and img_details[1]:
			is_private = item.image.startswith("/private/files/")

			with open(get_files_path(img_details[0].strip("/"), is_private=is_private), "rb") as image_file:
				image_info["image"]["attachment"] = base64.b64encode(image_file.read())
			image_info["image"]["filename"] = img_details[0]

			#to avoid 422 : Unprocessable Entity
			if not image_info["image"]["attachment"] or not image_info["image"]["filename"]:
				return False

		elif item.image.startswith("http") or item.image.startswith("ftp"):
			if validate_image_url(item.image):
				#to avoid 422 : Unprocessable Entity
				image_info["image"]["src"] = item.image

		if image_info["image"]:
			if not item_image_exists(item.magento_product_id, image_info):
				# to avoid image duplication
				post_request("/admin/products/{0}/images.json".format(item.magento_product_id), image_info)


def update_variant_item(new_item, item_code_list):
	for i, name in enumerate(item_code_list):
		erp_item = frappe.get_doc("Item", name)
		erp_item.flags.ignore_mandatory = True
		erp_item.magento_product_id = new_item['product']["variants"][i].get("id")
		erp_item.magento_variant_id = new_item['product']["variants"][i].get("id")
		erp_item.save()

def get_variant_attributes(item, price_list, warehouse):
	options, variant_list, variant_item_name, attr_sequence = [], [], [], []
	attr_dict = {}

	for i, variant in enumerate(frappe.get_all("Item", filters={"variant_of": item.get("name")},
		fields=['name'])):

		item_variant = frappe.get_doc("Item", variant.get("name"))
		variant_list.append(get_price_and_stock_details(item_variant, warehouse, price_list))

		for attr in item_variant.get('attributes'):
			if attr.attribute not in attr_sequence:
				attr_sequence.append(attr.attribute)

			if not attr_dict.get(attr.attribute):
				attr_dict.setdefault(attr.attribute, [])

			attr_dict[attr.attribute].append(attr.attribute_value)

			if attr.idx <= 3:
				variant_list[i]["option"+cstr(attr.idx)] = attr.attribute_value

		variant_item_name.append(item_variant.name)

	for i, attr in enumerate(attr_sequence):
		options.append({
			"name": attr,
			"position": i+1,
			"values": list(set(attr_dict[attr]))
		})

	return variant_list, options, variant_item_name

def get_price_and_stock_details(item, warehouse, price_list):
	qty = frappe.db.get_value("Bin", {"item_code":item.get("item_code"), "warehouse": warehouse}, "actual_qty")
	price = frappe.db.get_value("Item Price",
			{"price_list": price_list, "item_code":item.get("item_code")}, "price_list_rate")

	item_price_and_quantity = {
		"price": flt(price)
	}

	if item.net_weight:
		if item.weight_uom and item.weight_uom.lower() in ["kg", "g", "oz", "lb"]:
			item_price_and_quantity.update({
				"weight_unit": item.weight_uom.lower(),
				"weight": item.net_weight,
				"grams": get_weight_in_grams(item.net_weight, item.weight_uom)
			})


	if item.get("sync_qty_with_magento"):
		item_price_and_quantity.update({
			"inventory_quantity": cint(qty) if qty else 0,
			"inventory_management": "magento"
		})

	if item.magento_variant_id:
		item_price_and_quantity["id"] = item.magento_variant_id

	return item_price_and_quantity

def get_weight_in_grams(weight, weight_uom):
	convert_to_gram = {
		"kg": 1000,
		"lb": 453.592,
		"oz": 28.3495,
		"g": 1
	}

	return weight * convert_to_gram[weight_uom.lower()]

def trigger_update_item_stock(doc, method):
	if doc.flags.via_stock_ledger_entry:
		magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")
		if magento_settings.magento_url and magento_settings.enable_magento:
			update_item_stock(doc.item_code, magento_settings, doc)

def update_item_stock_qty():
	magento_settings = frappe.get_doc("Magento Settings", "Magento Settings")
	for item in frappe.get_all("Item", fields=['name', "item_code"],
		filters={"sync_with_magento": 1, "disabled": ("!=", 1), 'magento_variant_id': ('!=', '')}):
		try:
			update_item_stock(item.item_code, magento_settings)
		except MagentoError as e:
			make_magento_log(title=e.message, status="Error", method="sync_magento_items", message=frappe.get_traceback(),
				request_data=item, exception=True)

		except Exception as e:
			if e.args[0] and e.args[0].startswith("402"):
				raise e
			else:
				make_magento_log(title=e.message, status="Error", method="sync_magento_items", message=frappe.get_traceback(),
					request_data=item, exception=True)

def update_item_stock(item_code, magento_settings, bin=None):
	item = frappe.get_doc("Item", item_code)
	if item.sync_qty_with_magento:
		if not bin:
			bin = get_bin(item_code, magento_settings.warehouse)

		if not item.magento_product_id and not item.variant_of:
			sync_item_with_magento(item, magento_settings.price_list, magento_settings.warehouse)

		if item.sync_with_magento and item.magento_product_id and magento_settings.warehouse == bin.warehouse:
			if item.variant_of:
				item_data, resource = get_product_update_dict_and_resource(frappe.get_value("Item",
					item.variant_of, "magento_product_id"), item.magento_variant_id, is_variant=True,
					actual_qty=bin.actual_qty)
			else:
				item_data, resource = get_product_update_dict_and_resource(item.magento_product_id,
					item.magento_variant_id, actual_qty=bin.actual_qty)

			try:
				put_request(resource, item_data)
			except requests.exceptions.HTTPError as e:
				if e.args[0] and e.args[0].startswith("404"):
					make_magento_log(title=e.message, status="Error", method="sync_magento_items", message=frappe.get_traceback(),
						request_data=item_data, exception=True)
					disable_magento_sync_for_item(item)
				else:
					raise e

def get_product_update_dict_and_resource(magento_product_id, magento_variant_id, is_variant=False, actual_qty=0):
	"""
	JSON required to update product

	item_data =	{
		"product": {
			"id": 3649706435 (magento_product_id),
			"variants": [
				{
					"id": 10577917379 (magento_variant_id),
					"inventory_management": "magento",
					"inventory_quantity": 10
				}
			]
		}
	}
	"""

	item_data = {
		"product": {
			"variants": []
		}
	}

	varient_data = {
		"id": magento_variant_id,
		"inventory_quantity": cint(actual_qty),
		"inventory_management": "magento"
	}

	if is_variant:
		item_data = {
			"variant": varient_data
		}
		resource = "admin/variants/{}.json".format(magento_variant_id)
	else:
		item_data["product"]["id"] = magento_product_id
		item_data["product"]["variants"].append(varient_data)
		resource = "admin/products/{}.json".format(magento_product_id)

	return item_data, resource
