from app import db


class CodeInspection(db.Model):
    __tablename__ = 'inspections'
    id = db.Column(db.Integer, primary_key=True)
    changeset_id = db.Column(db.Integer, db.ForeignKey('changesets.id'))
    inspection_number = db.Column(db.Integer)
    inspection_url = db.Column(db.String(120))
    status = db.Column(db.String(20))
    sha1 = db.Column(db.String(40), index=True)

    def __init__(self, changeset_id = None, inspection_number = None, inspection_url = None, status = None, sha1 = None):
        self.changeset_id = changeset_id
        self.inspection_number = inspection_number
        self.inspection_url = inspection_url
        self.status = status
        self.sha1 = sha1

    def __str__(self):
        return  str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))

