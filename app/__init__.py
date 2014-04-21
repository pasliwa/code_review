from flask import Flask
# noinspection PyUnresolvedReferences
from flask.ext.mail import Mail
# noinspection PyUnresolvedReferences
from flask.ext.security import Security, SQLAlchemyUserDatastore
# noinspection PyUnresolvedReferences
from flask.ext.sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config.from_object('config')
db = SQLAlchemy(app)

from app.model import User, Role

user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)
mail = Mail(app)

from app.jenkins import Jenkins
from mercurial import Repo

repo = Repo(app.config["REPO_PATH"])
jenkins = Jenkins(app.config["JENKINS_URL"], app, repo)

from app import view
from app import utils
from app import routes
from app import logs


