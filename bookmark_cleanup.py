from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///testing.db"
db = SQLAlchemy(app)

db.create_all()

from app.mercurial import Repo


repo = Repo("../repository/project_1")

from app.model import Changeset, Review, User

merged_reviews = Review.query.filter(Review.status == "MERGED").all()
bookmarks = repo.hg_bookmarks()


for merged_review in merged_reviews:
    if merged_review.bookmark in bookmarks:
        repo.hg_bookmark(bookmark=merged_review.bookmark, delete=True)
    
abandoned_reviews = Review.query.filter(Review.status == "ABANDONED").all()


for abandoned_review in abandoned_reviews:
    if abandoned_review.bookmark in bookmarks:
        repo.hg_bookmark(bookmark=abandoned_review.bookmark, delete=True)
    
repo.hg_commit("Bookmark cleanup")
repo.hg_push()
