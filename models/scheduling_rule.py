# -*- coding: utf-8 -*- 

import datetime

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare, float_round, float_is_zero
from odoo.tools import format_datetime
import ast
from datetime import datetime, timedelta
from odoo.osv.expression import DOMAIN_OPERATORS

SPECIAL_DOMAIN_LEAFS = {
    'today': datetime.now().date(),
    'Today': datetime.now().date(),
    'current_date': datetime.now(),
    'now': datetime.now(),
    'Now': datetime.now(),
    'current_time': datetime.now(),
    'timedelta': timedelta,
}
DOMAIN_VAR_PART_POSITION = 2
COEFFICIENT_INDEX = 0
NOTE_INDEX = 1
COEFFICIENT_MIN = 1
ACCEPTED_FIELDS_TYPE_AS_NOTES = ('integer','float','monetary')


class SchedulingRule(models.Model):
    _name = 'scheduling.rule'
    _description = 'Scheduling rule'

    model_id = fields.Many2one('ir.model', string='Model')
    model_name = fields.Char('Model', required=True)
    field_id = fields.Many2one('ir.model.fields', string='Field', required=True, ondelete='cascade')
    coefficient = fields.Float(string='Coefficient', required=True,default=1)
    active = fields.Boolean(string="Active", default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.user.company_id)
    line_ids = fields.One2many('scheduling.rule.line', 'scheduling_rule_id')

    @api.onchange('model_id')
    def _onchange_model_id(self):
        if self.model_id:
            self.model_name = self.model_id.model

    @api.model
    def _schedule_records(self, records):
        """ Universal scheduling method basing on the records
        :param Model records:records to be scheduled
        :return Dictionary of {record.id:record_average}:"""
        records_rating = {}
        records_average = {}
        # get the appropriate scheduling rules basing on the records to schedule
        applied_rules = self._get_scheduling_rules_by_record(records)
        # loop on the scheduling rules to apply each rule on the appropriate record,the appropriate record is the one matching to the domain of the rule
        for scheduling_rule in applied_rules.mapped('line_ids'):
            domain = self._parse_domain(scheduling_rule.domain)
            for match_record in self.env[records._name].search([('id', 'in', records.ids)] + domain):
                try:
                    old_coefficient = records_rating[match_record.id][COEFFICIENT_INDEX]
                    new_coefficient = old_coefficient + scheduling_rule.scheduling_rule_id.coefficient
                    old_note = records_rating[match_record.id][NOTE_INDEX]
                    new_note = old_note + (scheduling_rule.note * scheduling_rule.scheduling_rule_id.coefficient)
                    records_rating.update({match_record.id: (new_coefficient, new_note)})
                except KeyError as ke:
                    records_rating[match_record.id] = (scheduling_rule.scheduling_rule_id.coefficient,
                                                       scheduling_rule.note * scheduling_rule.scheduling_rule_id.coefficient)
        for scheduling_rule in applied_rules.filtered(lambda r:not r.line_ids and r.field_id.ttype in ACCEPTED_FIELDS_TYPE_AS_NOTES):
            # in this case we have not filter so we have to apply the rule on all the records
            for record in records:
                try:
                    old_coefficient = records_rating[record.id][COEFFICIENT_INDEX]
                    new_coefficient = old_coefficient + scheduling_rule.coefficient
                    old_note = records_rating[record.id][NOTE_INDEX]
                    new_note = old_note + (getattr(record,scheduling_rule.field_id.name) * scheduling_rule.coefficient)
                    records_rating.update({record.id: (new_coefficient, new_note)})
                except KeyError as ke:
                    records_rating[record.id] = (scheduling_rule.coefficient,
                                                getattr(record,scheduling_rule.field_id.name) * scheduling_rule.coefficient)
        for record_id, record_rating in records_rating.items():
            records_average.update({record_id: record_rating[NOTE_INDEX] / max(record_rating[COEFFICIENT_INDEX],COEFFICIENT_MIN)})
        return records_average

    def _get_scheduling_rules_by_record(self, records):
        return self.search([('model_name', '=', records._name)])

    @api.model
    def _parse_domain(self, domain):
        parsed_domain = []
        for domain_token in ast.literal_eval(domain):
            if domain_token in DOMAIN_OPERATORS:
                parsed_domain.append(domain_token)
                continue
            # convert the domain_token from tuple to list to modify it
            domain_token = list(domain_token)
            try:
                domain_var_part = domain_token.pop(DOMAIN_VAR_PART_POSITION)
                domain_parsed_part = eval(str(domain_var_part), SPECIAL_DOMAIN_LEAFS)
            except TypeError as te:
                raise ValidationError(_("Some scheduling rules are poorly formed,All the parts of the rules must be string"))
            domain_token.insert(DOMAIN_VAR_PART_POSITION, str(domain_parsed_part))
            parsed_domain.append(tuple(domain_token))
        return parsed_domain


class SchedulingRuleLine(models.Model):
    _name = 'scheduling.rule.line'
    _description = 'Scheduling rule line'

    scheduling_rule_id = fields.Many2one('scheduling.rule', ondelete='cascade')
    model_name = fields.Char('Model',related='scheduling_rule_id.model_name')
    note = fields.Float(string='Note', default=False, required=True)
    domain = fields.Text(string='Domain', required=True)
