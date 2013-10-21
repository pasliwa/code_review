from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.types import DateTime
from database import Base
import datetime

class Review(Base):
    __tablename__ = 'reviews'
    id = Column(Integer, primary_key=True)
    owner = Column(String(50))
    owner_email = Column(String(120))
    created_date = Column(DateTime, default=datetime.datetime.utcnow)
    title = Column(String(120))
    sha1 = Column(String(40), index=True)
    builds = relationship("Build")


    def __init__(self, owner=None, owner_email=None, title=None, sha1=None):
        self.owner = owner
        self.owner_email = owner_email
        self.title = title
        self.sha1 = sha1

class Build(Base):
    __tablename__ = 'builds'
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey('reviews.id'))
    build_number = Column(Integer)
    build_url = Column(String(120))

    def __init__(self, review_id = None, build_no = None, build_url = None):
        self.review_id = review_id
        self.build_number = build_no
        self.build_url = build_url
