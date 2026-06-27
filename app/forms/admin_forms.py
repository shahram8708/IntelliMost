import pytz
from flask_wtf import FlaskForm
from wtforms import (StringField, EmailField, SelectField, IntegerField, FloatField,
                     DateField, BooleanField, TextAreaField, SubmitField)
from wtforms.validators import DataRequired, Email, Optional, Length, NumberRange

ROLE_CHOICES = [("admin", "Admin"), ("plant_manager", "Plant Manager"),
                ("industrial_engineer", "Industrial Engineer"), ("qa_manager", "QA Manager"),
                ("shift_supervisor", "Shift Supervisor"), ("operator", "Operator"),
                ("super_admin", "Super Admin")]
TZ_CHOICES = [(tz, tz) for tz in pytz.common_timezones]


class InviteUserForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    full_name = StringField("Full Name", validators=[DataRequired(), Length(2, 150)])
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    plant_id = SelectField("Plant", coerce=int, validators=[Optional()])
    submit = SubmitField("Send Invitation")


class EditUserForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(2, 150)])
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    plant_id = SelectField("Plant", coerce=int, validators=[Optional()])
    is_active = BooleanField("Active")
    is_locked = BooleanField("Locked")
    phone = StringField("Phone", validators=[Optional(), Length(0, 20)])
    department = StringField("Department", validators=[Optional(), Length(0, 100)])
    submit = SubmitField("Save")


class PlantForm(FlaskForm):
    name = StringField("Plant Name", validators=[DataRequired(), Length(2, 150)])
    location = StringField("Location", validators=[Optional(), Length(0, 255)])
    timezone = SelectField("Timezone", choices=TZ_CHOICES, default="Asia/Kolkata",
                           validators=[DataRequired()])
    industry_type = StringField("Industry Type", validators=[DataRequired(), Length(2, 100)])
    subscription_tier = SelectField("Subscription Tier",
                                    choices=[("starter", "Starter"), ("professional", "Professional"),
                                             ("enterprise", "Enterprise")], validators=[DataRequired()])
    contact_email = EmailField("Contact Email", validators=[Optional(), Email()])
    contact_phone = StringField("Contact Phone", validators=[Optional(), Length(0, 20)])
    submit = SubmitField("Save Plant")


class ProductionLineForm(FlaskForm):
    line_name = StringField("Line Name", validators=[DataRequired(), Length(2, 100)])
    line_code = StringField("Line Code", validators=[Optional(), Length(0, 50)])
    target_output_per_shift = IntegerField("Target Output / Shift",
                                           validators=[DataRequired(), NumberRange(min=1)], default=1000)
    shift_duration_hours = FloatField("Shift Duration (hours)", default=8.0,
                                      validators=[DataRequired(), NumberRange(min=0.5)])
    planned_break_minutes = IntegerField("Planned Break (min)", default=30,
                                         validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField("Save Line")


class MachineForm(FlaskForm):
    machine_name = StringField("Machine Name", validators=[DataRequired(), Length(2, 100)])
    machine_code = StringField("Machine Code", validators=[Optional(), Length(0, 50)])
    machine_type = StringField("Machine Type", validators=[DataRequired(), Length(2, 100)])
    manufacturer = StringField("Manufacturer", validators=[Optional(), Length(0, 100)])
    model_number = StringField("Model Number", validators=[Optional(), Length(0, 100)])
    line_id = SelectField("Line", coerce=int, validators=[DataRequired()])
    installation_date = DateField("Installation Date", validators=[Optional()])
    submit = SubmitField("Save Machine")


class SkuForm(FlaskForm):
    sku_code = StringField("SKU Code", validators=[DataRequired(), Length(1, 50)])
    sku_name = StringField("SKU Name", validators=[DataRequired(), Length(2, 200)])
    description = TextAreaField("Description", validators=[Optional()])
    unit_of_measure = StringField("Unit of Measure", default="units",
                                  validators=[DataRequired(), Length(1, 20)])
    standard_batch_size = IntegerField("Standard Batch Size", validators=[Optional(), NumberRange(min=1)])
    submit = SubmitField("Save SKU")


class ReasonCodeForm(FlaskForm):
    code = StringField("Code", validators=[DataRequired(), Length(1, 50)])
    label = StringField("Label", validators=[DataRequired(), Length(1, 150)])
    category = SelectField("Category", choices=[("equipment_failure", "Equipment Failure"),
                                                ("planned_maintenance", "Planned Maintenance"),
                                                ("changeover", "Changeover"), ("process", "Process"),
                                                ("utilities", "Utilities"), ("quality", "Quality"),
                                                ("other", "Other")], validators=[DataRequired()])
    parent_id = SelectField("Parent", coerce=int, validators=[Optional()])
    level = IntegerField("Level", default=1, validators=[DataRequired(), NumberRange(min=1, max=3)])
    submit = SubmitField("Save Reason Code")


class ProfileForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(2, 150)])
    phone = StringField("Phone", validators=[Optional(), Length(0, 20)])
    department = StringField("Department", validators=[Optional(), Length(0, 100)])
    most_certification_level = StringField("MOST Certification Level",
                                           validators=[Optional(), Length(0, 50)])
    submit = SubmitField("Save Profile")
