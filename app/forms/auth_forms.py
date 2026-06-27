import re
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, EmailField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError


def strong_password(form, field):
    p = field.data or ""
    if len(p) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if not re.search(r"[A-Za-z]", p) or not re.search(r"\d", p):
        raise ValidationError("Password must include letters and numbers.")


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Sign In")


class RegisterForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(2, 150)])
    password = PasswordField("Password", validators=[DataRequired(), Length(8, 128), strong_password])
    confirm_password = PasswordField("Confirm Password",
                                     validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Create Account")


class ForgotPasswordForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Send Reset Link")


class PasswordResetForm(FlaskForm):
    password = PasswordField("New Password", validators=[DataRequired(), Length(8, 128), strong_password])
    confirm_password = PasswordField("Confirm Password",
                                     validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Reset Password")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(8, 128), strong_password])
    confirm_password = PasswordField("Confirm Password",
                                     validators=[DataRequired(), EqualTo("new_password")])
    submit = SubmitField("Update Password")
