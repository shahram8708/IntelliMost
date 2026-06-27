from flask_wtf import FlaskForm
from wtforms import SelectField, DateField, SelectMultipleField, SubmitField, StringField
from wtforms.validators import DataRequired, Optional

REPORT_TYPES = [("shift_report", "Shift Report"), ("weekly_summary", "Weekly Summary"),
                ("most_comparison", "MOST Comparison"), ("capa_aging", "CAPA Aging"),
                ("rejection_trend", "Rejection Trend"), ("downtime", "Downtime"),
                ("oee_trend", "OEE Trend"), ("executive_summary", "Executive Summary")]


class ReportForm(FlaskForm):
    report_type = SelectField("Report Type", choices=REPORT_TYPES, validators=[DataRequired()])
    start_date = DateField("Start Date", validators=[Optional()])
    end_date = DateField("End Date", validators=[Optional()])
    line_ids = SelectMultipleField("Lines", coerce=int, validators=[Optional()])
    format = SelectField("Format", choices=[("pdf", "PDF"), ("excel", "Excel")], validators=[DataRequired()])
    submit = SubmitField("Generate")


class ScheduledReportForm(FlaskForm):
    report_type = SelectField("Report Type", choices=REPORT_TYPES, validators=[DataRequired()])
    frequency = SelectField("Frequency", choices=[("daily", "Daily"), ("weekly", "Weekly"),
                                                  ("monthly", "Monthly")], validators=[DataRequired()])
    recipients = StringField("Recipients (comma separated)", validators=[DataRequired()])
    format = SelectField("Format", choices=[("pdf", "PDF"), ("excel", "Excel")], validators=[DataRequired()])
    submit = SubmitField("Schedule")
