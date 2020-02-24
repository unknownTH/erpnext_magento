from __future__ import unicode_literals
import frappe
from frappe import _
import json, math, time, pytz
from .exceptions import MagentoError
from frappe.utils import get_request_session, get_datetime, get_time_zone, encode

def get_magento_settings():
	d = frappe.get_doc("Magento Settings")
	
	if d.magento_url:
		if d.password:
			d.password = d.get_password()
		else:
			frappe.throw(_("Magento Passwort is not configured on Magento Settings"), MagentoError)

		return d.as_dict()

	else:
		frappe.throw(_("Magento store URL is not configured on Magento Settings"), MagentoError)

def get_request(path, settings=None):
	if not settings:
		settings = get_magento_settings()

	s = get_request_session()
	url = get_magento_url(path, settings)
	r = s.get(url, headers=get_header(settings))
	r.raise_for_status()
	return r.json()

def post_request(path, data):
	settings = get_magento_settings()
	s = get_request_session()
	url = get_magento_url(path, settings)
	r = s.post(url, data=json.dumps(data), headers=get_header(settings))
	r.raise_for_status()
	return r.json()

def put_request(path, data):
	settings = get_magento_settings()
	s = get_request_session()
	url = get_magento_url(path, settings)
	r = s.put(url, data=json.dumps(data), headers=get_header(settings))
	r.raise_for_status()
	return r.json()

def delete_request(path):
	s = get_request_session()
	url = get_magento_url(path)
	r = s.delete(url)
	r.raise_for_status()

def get_magento_url(path, settings):
	if settings['app_type'] == "Private":
		return 'https://{}:{}@{}/{}'.format(settings['api_key'], settings['password'], settings['magento_url'], path)
	else:
		return 'https://{}/{}'.format(settings['magento_url'], path)

def get_header(settings):
	header = {'Content-Type': 'application/json'}

	if settings['app_type'] == "Private":
		return header
	else:
		header["X-Magento-Access-Token"] = settings['access_token']
		return header

def get_filtering_condition():
	magento_settings = get_magento_settings()
	if magento_settings.last_sync_datetime:

		last_sync_datetime = get_datetime(magento_settings.last_sync_datetime)
		timezone = pytz.timezone(get_time_zone())
		timezone_abbr = timezone.localize(last_sync_datetime, is_dst=False)

		utc_dt = timezone_abbr.astimezone (pytz.utc)
		return 'updated_at_min="{0}"'.format(utc_dt.strftime("%Y-%m-%d %H:%M:%S"))
	return ''

def get_total_pages(resource, ignore_filter_conditions=False):
	filter_condition = ""

	if not ignore_filter_conditions:
		filter_condition = get_filtering_condition()
	
	count = get_request('/admin/{0}&{1}'.format(resource, filter_condition))
	return int(math.ceil(count.get('count', 0) / 250))

def get_country():
	return get_request('/admin/countries.json')['countries']

def get_magento_items(ignore_filter_conditions=False):
	magento_products = []

	filter_condition = ''
	if not ignore_filter_conditions:
		filter_condition = get_filtering_condition().encode("utf-8")

	for page_idx in xrange(0, get_total_pages("products/count.json?", ignore_filter_conditions) or 1):
		magento_products.extend(get_request('/admin/products.json?limit=250&page={0}&{1}'.format(page_idx+1,
			filter_condition))['products'])

	return magento_products

def get_magento_item_image(magento_product_id):
	return get_request("/admin/products/{0}/images.json".format(magento_product_id))["images"]

def get_magento_orders(ignore_filter_conditions=False):
	magento_orders = []

	filter_condition = ''

	if not ignore_filter_conditions:
		filter_condition = get_filtering_condition()

	for page_idx in xrange(0, get_total_pages("orders/count.json?status=any", ignore_filter_conditions) or 1):
		magento_orders.extend(get_request('/admin/orders.json?status=any&limit=250&page={0}&{1}'.format(page_idx+1,
			filter_condition))['orders'])
	return magento_orders

def get_magento_customers(ignore_filter_conditions=False):
	magento_customers = []

	filter_condition = ''

	if not ignore_filter_conditions:
		filter_condition = get_filtering_condition()

	for page_idx in xrange(0, get_total_pages("customers/count.json?", ignore_filter_conditions) or 1):
		magento_customers.extend(get_request('/admin/customers.json?limit=250&page={0}&{1}'.format(page_idx+1,
			filter_condition))['customers'])
	return magento_customers
