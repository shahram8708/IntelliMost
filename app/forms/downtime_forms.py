from flask_wtf import FlaskForm
from wtforms import SelectField, DateTimeLocalField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional


class DowntimeForm(FlaskForm):
    machine_id = SelectField("Machine", coerce=int, validators=[DataRequired()])
    shift_id = SelectField("Shift", coerce=int, validators=[DataRequired()])
    event_type = SelectField("Event Type",
                             choices=[("unplanned", "Unplanned Downtime"),
                                      ("planned_maintenance", "Planned Maintenance"),
                                      ("changeover", "Changeover"),
                                      ("breakdown", "Breakdown")],
                             validators=[DataRequired()])
    reason_code_id = SelectField("Reason Code", coerce=int, validators=[Optional()])
    start_time = DateTimeLocalField("Start Time", format="%Y-%m-%dT%H:%M",
                                    validators=[DataRequired()])
    end_time = DateTimeLocalField("End Time", format="%Y-%m-%dT%H:%M",
                                  validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Submit")
