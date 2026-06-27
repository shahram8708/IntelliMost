from flask_wtf import FlaskForm
from wtforms import SelectField, IntegerField, StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange, Length


class RejectionForm(FlaskForm):
    shift_id = SelectField("Shift", coerce=int, validators=[DataRequired()])
    machine_id = SelectField("Machine", coerce=int, validators=[Optional()])
    sku_id = SelectField("SKU", coerce=int, validators=[Optional()])
    quantity_rejected = IntegerField("Quantity Rejected",
                                     validators=[DataRequired(), NumberRange(min=1)])
    defect_type = StringField("Defect Type", validators=[DataRequired(), Length(1, 150)])
    defect_description = TextAreaField("Description", validators=[Optional()])
    probable_cause = StringField("Probable Cause", validators=[Optional(), Length(0, 255)])
    quality_check_point = StringField("QC Check Point", validators=[Optional(), Length(0, 150)])
    batch_reference = StringField("Batch Reference", validators=[Optional(), Length(0, 100)])
    submit = SubmitField("Log Rejection")


class OutputLogForm(FlaskForm):
    shift_id = SelectField("Shift", coerce=int, validators=[DataRequired()])
    quantity = IntegerField("Quantity Produced",
                            validators=[DataRequired(), NumberRange(min=1)])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Log Output")
