import datetime
from app import db


class Changeset(db.Model):

    __tablename__ = 'changesets'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('review.id'))
    owner = db.Column(db.String(50))
    owner_email = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    title = db.Column(db.String(120))
    sha1 = db.Column(db.String(40), index=True)
    status = db.Column(db.String(20))
    bookmark = db.Column(db.String(120))
    builds = db.relationship("Build")
    inspections = db.relationship("CodeInspection")

    def __init__(self, owner=None, owner_email=None, title=None, sha1=None, bookmark=None, status=None):
        self.owner = owner
        self.owner_email = owner_email
        self.title = title
        self.sha1 = sha1
        self.bookmark = bookmark
        self.status = status

    def __str__(self):
        return  str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))
