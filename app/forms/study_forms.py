from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, TextAreaField, SelectField, IntegerField, FloatField,
                     DateField, SubmitField, HiddenField, RadioField)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class StudyMetaForm(FlaskForm):
    study_name = StringField("Study Name", validators=[DataRequired(), Length(2, 200)])
    workstation_id = SelectField("Workstation", coerce=int, validators=[DataRequired()])
    sku_id = SelectField("SKU", coerce=int, validators=[Optional()])
    shift_observed = StringField("Shift Observed", validators=[Optional(), Length(0, 20)])
    study_date = DateField("Study Date", validators=[DataRequired()])
    sample_size = IntegerField("Sample Size", validators=[DataRequired(), NumberRange(min=1)], default=1)
    allowance_percent = FloatField("Allowance %", validators=[DataRequired(), NumberRange(min=0, max=100)],
                                   default=15.0)
    working_conditions = TextAreaField("Working Conditions", validators=[Optional()])
    observation_method = SelectField("Observation Method",
                                     choices=[("direct_entry", "Direct Entry"),
                                              ("manual_timer", "Manual Timer"),
                                              ("video_upload", "Video Upload")],
                                     validators=[DataRequired()])
    submit = SubmitField("Next")


class VideoUploadForm(FlaskForm):
    video_file = FileField("Video (MP4)", validators=[Optional(), FileAllowed(["mp4"], "MP4 only")])
    submit = SubmitField("Next")


class ElementForm(FlaskForm):
    element_name = StringField("Element Name", validators=[DataRequired(), Length(1, 200)])
    element_description = TextAreaField("Description", validators=[Optional()])
    most_method = RadioField("MOST Method",
                             choices=[("general_move", "General Move"),
                                      ("controlled_move", "Controlled Move"),
                                      ("tool_use", "Tool Use")],
                             default="general_move", validators=[DataRequired()])
    submit = SubmitField("Add Element")


class AllowanceForm(FlaskForm):
    allowance_percent = FloatField("Allowance %", validators=[DataRequired(), NumberRange(min=0, max=100)])
    submit = SubmitField("Recalculate")
