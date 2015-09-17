from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///testing.db"
db = SQLAlchemy(app)

db.create_all()

from app.mercurial import Repo

repo = Repo(app.config["REPO_PATH"])

from app.model import Changeset, Review, User

merged_reviews = Review.query.filter(Review.status == "MERGED").all()

for merged_review in merged_reviews:
    repo.hg_bookmark(bookmark=merged_review.bookmark, delete=True)

repo.hg_push()
