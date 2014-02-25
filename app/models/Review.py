
import datetime
from sqlalchemy.sql.expression import or_, desc, asc, and_
from app import db


class Review(db.Model):
    __tablename__ = 'review'
    id = db.Column(db.Integer, primary_key=True)
    owner = db.Column(db.String(50))
    owner_email = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    close_date = db.Column(db.DateTime)
    title = db.Column(db.String(120))
    bookmark = db.Column(db.String(120))
    status = db.Column(db.String(20))
    target = db.Column(db.String(20))
    changesets = db.relationship("Changeset", order_by=desc("created_date"))

    def __init__(self, owner=None, owner_email=None, title=None, sha1=None, bookmark=None, status = None, target = None):
        self.owner = owner
        self.owner_email = owner_email
        self.title = title
        self.sha1 = sha1
        self.bookmark = bookmark
        self.status = status
        self.target = target

    def __str__(self):
        return  str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))
