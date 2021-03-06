from flask import Flask
# noinspection PyUnresolvedReferences
from flask.ext.mail import Mail
# noinspection PyUnresolvedReferences
from flask.ext.security import Security, SQLAlchemyUserDatastore
# noinspection PyUnresolvedReferences
from flask.ext.sqlalchemy import SQLAlchemy
import pytz
from datetime import datetime

app = Flask(__name__)
app.config.from_object('config')
db = SQLAlchemy(app)

from app.model import User, Role

user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)
mail = Mail(app)

from app.jenkins import Jenkins
from app.mercurial import Repo
from app.collab import CodeCollaborator

repo = Repo(app.config["REPO_PATH"])
jenkins = Jenkins(app.config["JENKINS_URL"])
cc = CodeCollaborator(app.config["CC_BIN"], app.config["CC_REVIEW_URL"],
                      app.config["REPO_PATH"])

from app import view
from app import utils
from app import routes

def utc_to_local(utc_dt):
    if not type(utc_dt) is datetime:
        utc_dt = datetime.strptime(utc_dt, '%Y-%m-%d %H:%M:%S.%f')
    local_tz = pytz.timezone('Europe/Warsaw')
    local_dt = utc_dt.replace(tzinfo=pytz.utc).astimezone(local_tz)
    return local_tz.normalize(local_dt).strftime("%Y-%m-%d %H:%M")
    
app.jinja_env.globals.update(utc_to_local=utc_to_local)
