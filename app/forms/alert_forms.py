from flask_wtf import FlaskForm
from wtforms import (StringField, SelectField, FloatField, IntegerField, BooleanField,
                     SelectMultipleField, TextAreaField, SubmitField)
from wtforms.validators import DataRequired, Optional, NumberRange

METRICS = [("rejection_rate", "Rejection Rate %"), ("downtime_duration", "Downtime Duration (min)"),
           ("oee_percent", "OEE %"), ("output_attainment", "Output Attainment %"),
           ("efficiency_ratio", "Efficiency Ratio")]


class AlertRuleForm(FlaskForm):
    rule_name = StringField("Rule Name", validators=[DataRequired()])
    metric_name = SelectField("Metric", choices=METRICS, validators=[DataRequired()])
    operator = SelectField("Operator", choices=[("gt", ">"), ("lt", "<"), ("gte", ">="),
                                                ("lte", "<="), ("eq", "=")], validators=[DataRequired()])
    threshold_value = FloatField("Threshold", validators=[DataRequired()])
    time_window_minutes = IntegerField("Time Window (min)", default=60,
                                       validators=[DataRequired(), NumberRange(min=1)])
    line_id = SelectField("Line", coerce=int, validators=[Optional()])
    recipient_user_ids = SelectMultipleField("Recipients", coerce=int, validators=[DataRequired()])
    escalation_timeout_minutes = IntegerField("Escalation Timeout (min)", default=60,
                                              validators=[DataRequired(), NumberRange(min=1)])
    escalation_user_ids = SelectMultipleField("Escalation Recipients", coerce=int, validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Rule")


class AcknowledgeAlertForm(FlaskForm):
    action = SelectField("Action", choices=[("investigate", "Investigate"),
                                            ("capa_raised", "Raise CAPA"),
                                            ("dismissed_reason", "Dismiss")], validators=[DataRequired()])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Acknowledge")
