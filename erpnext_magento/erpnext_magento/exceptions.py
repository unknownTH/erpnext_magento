from __future__ import unicode_literals
import frappe

class MagentoError(frappe.ValidationError): pass
class MagentoSetupError(frappe.ValidationError): pass