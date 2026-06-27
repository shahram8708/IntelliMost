from flask_wtf import FlaskForm
from wtforms import TextAreaField, DateField, SubmitField
from wtforms.validators import DataRequired


class DismissForm(FlaskForm):
    dismissed_reason = TextAreaField("Reason", validators=[DataRequired()])
    submit = SubmitField("Dismiss")


class DeferForm(FlaskForm):
    deferred_until = DateField("Defer Until", validators=[DataRequired()])
    submit = SubmitField("Defer")
