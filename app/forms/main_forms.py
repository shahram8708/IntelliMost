from flask_wtf import FlaskForm
from wtforms import StringField, EmailField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email, Optional, Length


class DemoRequestForm(FlaskForm):
    name = StringField("Full Name", validators=[DataRequired(), Length(2, 150)])
    email = EmailField("Work Email", validators=[DataRequired(), Email()])
    company = StringField("Company", validators=[DataRequired(), Length(2, 200)])
    role = SelectField("Role", choices=[("plant_manager", "Plant Manager"),
                                        ("industrial_engineer", "Industrial Engineer"),
                                        ("qa_manager", "QA Manager"), ("other", "Other")],
                       validators=[DataRequired()])
    facility_type = SelectField("Facility Type", choices=[("pharmaceutical", "Pharmaceutical"),
                                                          ("process", "Process Manufacturing"),
                                                          ("fmcg", "FMCG"), ("other", "Other")],
                                validators=[DataRequired()])
    phone = StringField("Phone", validators=[Optional(), Length(0, 20)])
    submit = SubmitField("Request Free Demo")


class ContactForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(2, 150)])
    email = EmailField("Email", validators=[DataRequired(), Email()])
    company = StringField("Company", validators=[Optional(), Length(0, 200)])
    message = TextAreaField("Message", validators=[DataRequired(), Length(2, 2000)])
    submit = SubmitField("Send Message")
