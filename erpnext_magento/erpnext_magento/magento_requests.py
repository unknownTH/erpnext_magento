from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import get_request_session, get_datetime, get_time_zone, encode
import json, math, time, pytz
from erpnext_magento.erpnext_magento.exceptions import MagentoError
from erpnext_magento.erpnext_magento.utils import make_magento_log

def get_magento_settings():
	d = frappe.get_doc("Magento Settings")
	
	if d.magento_url:
		if d.api_access_token:
			return d.as_dict()

		else:
			frappe.throw(_("Magento API access token is not configured on Magento Settings"), MagentoError)

	else:
		frappe.throw(_("Magento store URL is not configured on Magento Settings"), MagentoError)

def get_request(path, settings=None):
	if not settings:
		settings = get_magento_settings()

	s = get_request_session()
	url = get_request_url(path, settings)
	r = s.get(url, headers=get_header(settings))
	r.raise_for_status()
	return r.json()

def post_request(path, data):
	settings = get_magento_settings()
	s = get_request_session()
	url = get_request_url(path, settings)
	r = s.post(url, data=json.dumps(data), headers=get_header(settings))
	r.raise_for_status()
	return r.json()

def put_request(path, data):
	settings = get_magento_settings()
	s = get_request_session()
	url = get_request_url(path, settings)
	r = s.put(url, data=json.dumps(data), headers=get_header(settings))
	r.raise_for_status()
	return r.json()

def delete_request(path):
	s = get_request_session()
	url = get_request_url(path)
	r = s.delete(url)
	r.raise_for_status()

def get_request_url(path, settings):
	magento_url = settings['magento_url']
	
	if magento_url[-1] != "/":
		magento_url += "/"
	
	if "rest/V1/" in path:
		return '{0}{1}'.format(magento_url, path)
	
	else:
		return '{0}rest/V1/{1}'.format(magento_url, path)

def get_header(settings):
	header = {
		'Authorization': 'Bearer ' + settings['api_access_token'],
		'Content-Type': 'application/json',
		'Accept': 'application/json'
	}
	return header

def get_filtering_condition():
	magento_settings = get_magento_settings()
	if magento_settings.last_sync_datetime:

		last_sync_datetime = get_datetime(magento_settings.last_sync_datetime)
		timezone = pytz.timezone(get_time_zone())
		timezone_abbr = timezone.localize(last_sync_datetime, is_dst=False)

		utc_dt = timezone_abbr.astimezone (pytz.utc)
		filter = 'searchCriteria[filter_groups][0][filters][0][field]=updated_at\
&searchCriteria[filter_groups][0][filters][0][value]={0}\
&searchCriteria[filter_groups][0][filters][0][condition_type]=gt'.format(utc_dt.strftime("%Y-%m-%d %H:%M:%S"))
		return filter
	return ''

def get_total_pages(resource, ignore_filter_conditions=False):
	filter_condition = ""

	if not ignore_filter_conditions:
		filter_condition = get_filtering_condition()
	else:
		filter_condition = "searchCriteria"

	count = get_request('{0}?searchCriteria[pageSize]=1&{1}'.format(resource, filter_condition))
	return int(math.ceil(count.get('total_count') / 250))

# Delete
#def get_websites():
#	return get_request('store/websites')

def get_magento_parent_item_id(magento_item):
	for configurable_item in get_magento_configurable_items():
		if magento_item.get("id") in configurable_item.get("extension_attributes").get("configurable_product_links"):
			return configurable_item.get("id")

def get_magento_configurable_items():
	filter = "searchCriteria[filter_groups][0][filters][0][field]=type_id\
&searchCriteria[filter_groups][0][filters][0][value]=configurable\
&searchCriteria[filter_groups][0][filters][0][condition_type]=eq"

	return get_request("products?{0}".format(filter))['items']

def get_magento_item_price_by_website(magento_item, website_id):
	store_code = get_magento_store_code_by_website_id(website_id)
	item = get_request("{0}/rest/V1/products/{1}".format(store_code, magento_item.get("sku")))	
	return item.get("price")

def get_magento_website_name_by_id(website_id):
	websites = get_request("store/websites")
	for website in websites:
		if website.get("id") == website_id:
			return website.get("name")

def get_magento_country_name_by_id(country_id):
	countries = get_request('directory/countries')
	for country in countries:
		if country.get("id") == country_id:
			return country.get("full_name_locale")
	
	make_magento_log(title="Country not Found", status="Error", method="get_magento_country_name_by_id", message="No country with id {0}".format(country_id),
		request_data=country, exception=True)

def get_magento_country_id_by_name(country_name):
	countries = get_request('directory/countries')
	for country in countries:
		if country.get("full_name_locale") == country_name:
			return country.get("id")
	
	make_magento_log(title="Country not Found", status="Error", method="get_magento_country_id_by_name", message="No country with name {0}".format(country_name),
		request_data=country, exception=True)

def get_magento_region_id_by_name(region_name):
	countries = get_request('directory/countries')
	for country in countries:
		if country.get("available_regions"):
			for region in country.get("available_regions"):
				if region.get("name") == region_name:
					return region.get("id")
				
	make_magento_log(title="Region not Found", status="Error", method="get_magento_region_id_by_name", message="No Magento region with name {0}".format(region_name),
		request_data=country, exception=True)

def get_magento_item_attribute_details_by_code(item_attribute_code):
	return get_request("products/attributes/{0}".format(item_attribute_code))

def get_magento_item_attribute_details_by_name(item_attribute_name):
	for magento_item_attribute in get_request("products/attributes?searchCriteria")["items"]:
		if magento_item_attribute.get("default_frontend_label") == item_attribute_name:
			return magento_item_attribute

def get_magento_item_atrribute_values(attribute_id):
	attribute = get_request('products/attributes/{}'.format(attribute_id))

	return attribute.get("options")

def get_magento_store_code_by_website_id(website_id):
	# Only the store code of the fist maching store is returned.
	stores = get_request('store/storeViews')
	for store in stores:
		if store.get("website_id") == website_id:
			return store.get("code")

def get_magento_items(ignore_filter_conditions=False):
	magento_items = []

	filter_condition = ""
	sort_order = "searchCriteria[sortOrders][0][field]=type_id&searchCriteria[sortOrders][0][direction]=ASC"

	if not ignore_filter_conditions:
		filter_condition = get_filtering_condition()

	for page_idx in range(0, get_total_pages("products", ignore_filter_conditions) or 1):
		magento_items.extend(get_request('products?searchCriteria[pageSize]=250&searchCriteria[currentPage]={0}&{1}&{2}'\
			.format(page_idx+1,	filter_condition, sort_order))['items'])

	return magento_items

def get_magento_orders(ignore_filter_conditions=False):
	magento_orders = []

	filter_condition = ""

	if not ignore_filter_conditions:
		filter_condition = get_filtering_condition()	

	for page_idx in range(0, get_total_pages("orders", ignore_filter_conditions) or 1):
		magento_orders.extend(get_request('orders?searchCriteria[pageSize]=250&searchCriteria[currentPage]={0}&{1}'.format(page_idx+1,
			filter_condition))['items'])
	return magento_orders

def get_magento_customers(ignore_filter_conditions=False):
	magento_customers = []

	filter_condition = ""

	if not ignore_filter_conditions:
		filter_condition = get_filtering_condition()

	for page_idx in range(0, get_total_pages("customers/search", ignore_filter_conditions) or 1):
		magento_customers.extend(get_request('customers/search?searchCriteria[pageSize]=250&searchCriteria[currentPage]={0}&{1}'.format(page_idx+1,
			filter_condition))['items'])
	return magento_customers





