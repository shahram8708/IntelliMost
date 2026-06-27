from flask_wtf import FlaskForm
from wtforms import TextAreaField, SelectField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Optional


class RcaForm(FlaskForm):
    problem_statement = TextAreaField("Problem Statement", validators=[DataRequired()])
    why_1 = TextAreaField("Why 1", validators=[Optional()])
    why_2 = TextAreaField("Why 2", validators=[Optional()])
    why_3 = TextAreaField("Why 3", validators=[Optional()])
    why_4 = TextAreaField("Why 4", validators=[Optional()])
    why_5 = TextAreaField("Why 5", validators=[Optional()])
    root_cause_statement = TextAreaField("Root Cause Statement", validators=[Optional()])
    root_cause_category = SelectField("Root Cause Category",
                                      choices=[("", "Select..."), ("man", "Man"), ("machine", "Machine"),
                                               ("method", "Method"), ("material", "Material"),
                                               ("measurement", "Measurement"), ("environment", "Environment")],
                                      validators=[Optional()])
    similar_events_referenced = HiddenField()
    submit = SubmitField("Save RCA")
