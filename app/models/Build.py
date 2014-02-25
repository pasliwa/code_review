from app import db


class Build(db.Model):
    __tablename__ = 'builds'
    id = db.Column(db.Integer, primary_key=True)
    changeset_id = db.Column(db.Integer, db.ForeignKey('changesets.id'))
    build_number = db.Column(db.Integer)
    build_url = db.Column(db.String(120))
    status = db.Column(db.String(20))
    job_name = db.Column(db.String(30))
    scheduled = db.Column(db.String(30))

    def __init__(self, changeset_id = None, build_no = None, build_url = None, status = None, job_name = None):
        self.changeset_id = changeset_id
        self.build_number = build_no
        self.build_url = build_url
        self.status = status
        self.job_name = job_name

    def __str__(self):
        return  str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))
