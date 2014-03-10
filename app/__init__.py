from flask import Flask
from flask.ext.mail import Mail
from flask.ext.security import Security, SQLAlchemyUserDatastore
from flask.ext.sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config.from_object('config')
db = SQLAlchemy(app)

from app.model import User, Role

user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)
mail = Mail(app)

from app.jenkins import Jenkins
from mercurial import Repo2

repo = Repo2(app.config["REPO_PATH"])
jenkins = Jenkins(app.config["JENKINS_URL"], app, repo)

from app import view
from app import utils
from app import routes
from app import logs

