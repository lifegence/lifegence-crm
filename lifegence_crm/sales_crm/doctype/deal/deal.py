import frappe
from frappe.model.document import Document


class Deal(Document):
	def validate(self):
		self.set_probability_from_stage()
		self.calculate_weighted_value()

	def set_probability_from_stage(self):
		if self.stage:
			self.probability = frappe.db.get_value("Deal Stage", self.stage, "probability") or 0

	def calculate_weighted_value(self):
		self.weighted_value = (self.deal_value or 0) * (self.probability or 0) / 100
