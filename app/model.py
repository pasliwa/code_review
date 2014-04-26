import logging
import datetime

# noinspection PyUnresolvedReferences
from flask.ext.security import RoleMixin, UserMixin
from sqlalchemy.sql.expression import desc

from app import db

logger = logging.getLogger(__name__)

# Define models
roles_users = db.Table('roles_users',
                       db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
                       db.Column('role_id', db.Integer(), db.ForeignKey('role.id')))


class Role(db.Model, RoleMixin):
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    cc_login = db.Column(db.String(50))
    active = db.Column(db.Boolean())
    confirmed_at = db.Column(db.DateTime())
    roles = db.relationship('Role', secondary=roles_users,
                            backref=db.backref('users', lazy='dynamic'))


class Build(db.Model):
    __tablename__ = 'builds'
    id = db.Column(db.Integer, primary_key=True)
    changeset_id = db.Column(db.Integer, db.ForeignKey('changesets.id'))
    request_id = db.Column(db.String(36))
    build_number = db.Column(db.Integer)
    build_url = db.Column(db.String(120))
    status = db.Column(db.String(20))
    job_name = db.Column(db.String(30))
    scheduled = db.Column(db.String(30))

    def __init__(self, changeset_id=None, build_no=None, build_url=None, status=None, job_name=None):
        self.changeset_id = changeset_id
        self.build_number = build_no
        self.build_url = build_url
        self.status = status
        self.job_name = job_name

    def __str__(self):
        return str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))


class Changeset(db.Model):
    __tablename__ = 'changesets'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('review.id'))
    owner = db.Column(db.String(50))
    owner_email = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    title = db.Column(db.String(120))
    sha1 = db.Column(db.String(40), index=True, unique=True)
    status = db.Column(db.String(20)) # ACTIVE, ABANDONED
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
        return str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))


class CodeInspection(db.Model):
    __tablename__ = 'inspections'
    id = db.Column(db.Integer, primary_key=True)
    changeset_id = db.Column(db.Integer, db.ForeignKey('changesets.id'))
    inspection_number = db.Column(db.Integer)
    inspection_url = db.Column(db.String(120))
    status = db.Column(db.String(20))
    sha1 = db.Column(db.String(40), index=True)

    def __init__(self, changeset_id=None, inspection_number=None, inspection_url=None, status=None, sha1=None):
        self.changeset_id = changeset_id
        self.inspection_number = inspection_number
        self.inspection_url = inspection_url
        self.status = status
        self.sha1 = sha1

    def __str__(self):
        return str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))


class Review(db.Model):
    __tablename__ = 'review'
    id = db.Column(db.Integer, primary_key=True)
    owner = db.Column(db.String(50))
    owner_email = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    close_date = db.Column(db.DateTime)
    title = db.Column(db.String(120))
    bookmark = db.Column(db.String(120))
    status = db.Column(db.String(20))   # ACTIVE, MERGED, ABANDONED
    target = db.Column(db.String(20))
    changesets = db.relationship("Changeset", order_by=desc("created_date"))
    targets = db.relationship("Target", order_by=desc("name"))

    def __init__(self, owner=None, owner_email=None, title=None, bookmark=None, status=None):
        self.owner = owner
        self.owner_email = owner_email
        self.title = title
        self.bookmark = bookmark
        self.status = status

    #TODO: Test, that targets cannot duplicate
    #TODO: Test, that target must be one of targets
    #TODO: What happens on UI when targets list is empty
    #TODO: Test, that target cannot be set to something outside of targets list
    def add_targets(self, targets):
        existing_targets = set([rec.name for rec in self.targets])
        for target in list(set(targets) - existing_targets):
            self.targets.append(Target(target))
        if len(self.targets) == 0:
            logger.error("Empty targets list for review %d", self.id)
            self.target = None
        elif not self.target in set(targets) | existing_targets:
            self.target = self.targets[0].name

    def set_target(self, target):
        targets = set([rec.name for rec in self.targets])
        if not target in targets:
            raise Exception("Target %s is not allowed for review %d",
                            target, self.id)

    def __str__(self):
        return str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))


class Target(db.Model):
    __tablename__ = 'target'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('review.id'))
    name = db.Column(db.String(20))

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))
