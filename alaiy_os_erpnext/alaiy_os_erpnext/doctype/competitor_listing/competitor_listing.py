import frappe
from frappe.model.document import Document


class CompetitorListing(Document):

    def before_save(self):
        pass  # Extend with velocity-based revenue impact calc if needed
