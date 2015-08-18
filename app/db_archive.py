from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy

archiver_login = 'abc'
archiver_password = 'xyz'

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] =
db = SQLAlchemy(app)

db.create_all()

from app.model import Changeset, Review

from app.jira import integrate_all_old
from app.crypto import encryption

integrate_all_old(archiver_login, encryption(archiver_password))
