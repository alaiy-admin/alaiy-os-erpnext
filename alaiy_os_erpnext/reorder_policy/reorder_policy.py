import frappe
from frappe.model.document import Document


class ReorderPolicy(Document):

    def validate(self):
        if self.safety_stock and self.reorder_point and self.safety_stock > self.reorder_point:
            frappe.throw("Safety stock cannot be greater than reorder point.")
