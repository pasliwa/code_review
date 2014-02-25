from flask.ext.wtf import Form
from wtforms import TextField, BooleanField
from wtforms.validators import Required, Optional


class SearchForm(Form):
    title = TextField('title', description="title", validators=[Optional()])
    author = TextField('author', description="author", validators=[Optional()])
