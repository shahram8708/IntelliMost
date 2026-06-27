from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, TextAreaField, SelectField, DateField, SubmitField)
from wtforms.validators import DataRequired, Optional, Length


class CapaForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(2, 300)])
    severity = SelectField("Severity", choices=[("critical", "Critical"), ("major", "Major"),
                                                ("minor", "Minor")], validators=[DataRequired()])
    source_type = SelectField("Source", choices=[("alert", "Alert"), ("deviation", "Deviation"),
                                                 ("audit", "Audit"), ("customer_complaint", "Customer Complaint"),
                                                 ("self_initiated", "Self Initiated")], validators=[DataRequired()])
    source_description = StringField("Source Description", validators=[Optional(), Length(0, 300)])
    affected_machine_id = SelectField("Affected Machine", coerce=int, validators=[Optional()])
    affected_sku_id = SelectField("Affected SKU", coerce=int, validators=[Optional()])
    affected_batch = StringField("Affected Batch", validators=[Optional(), Length(0, 100)])
    deviation_description = TextAreaField("Deviation Description", validators=[DataRequired()])
    immediate_action = TextAreaField("Immediate Action", validators=[Optional()])
    owner_id = SelectField("Owner", coerce=int, validators=[DataRequired()])
    reviewer_id = SelectField("Reviewer", coerce=int, validators=[Optional()])
    due_date = DateField("Due Date", validators=[DataRequired()])
    priority = SelectField("Priority", choices=[("high", "High"), ("medium", "Medium"),
                                                ("low", "Low")], validators=[DataRequired()])
    submit = SubmitField("Create CAPA")


class CapaUpdateForm(FlaskForm):
    corrective_action = TextAreaField("Corrective Action", validators=[Optional()])
    preventive_action = TextAreaField("Preventive Action", validators=[Optional()])
    immediate_action = TextAreaField("Immediate Action", validators=[Optional()])
    root_cause_summary = TextAreaField("Root Cause Summary", validators=[Optional()])
    submit = SubmitField("Save Changes")


class CapaStatusForm(FlaskForm):
    new_status = SelectField("New Status", choices=[("open", "Open"), ("in_progress", "In Progress"),
                                                    ("pending_review", "Pending Review"),
                                                    ("closed", "Closed")], validators=[DataRequired()])
    closure_notes = TextAreaField("Closure Notes", validators=[Optional()])
    evidence = FileField("Evidence", validators=[Optional(),
                          FileAllowed(["jpg", "jpeg", "png", "pdf"], "Images or PDF only")])
    submit = SubmitField("Update Status")


class CapaCommentForm(FlaskForm):
    body = TextAreaField("Comment", validators=[DataRequired(), Length(1, 2000)])
    submit = SubmitField("Add Comment")
