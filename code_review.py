import os
import datetime
from sqlalchemy.sql.expression import or_
from flask import Flask, redirect, url_for
from flask.globals import request
from flask.templating import render_template
from hgapi import HgException
from CodeCollaborator import CodeCollaborator
from Jenkins import Jenkins
from Repo2 import Repo2
#from database import db_session, init_db
from flask.ext.sqlalchemy import SQLAlchemy
#from models import Review, Build



# host: pl-byd-srv01.emea.int.genesyslab.com:18080/view/8.5/job/iwd_8.5.000-REVIEW/build/api/json
# x-www-form-urlencoded
# json       {"parameter":[{"name":"BRANCH","value":"MASTER"}]}
# encoded post : j  son=%7B%22parameter%22%3A%5B%7B%22name%22%3A%22BRANCH%22%2C%22value%22%3A%22MASTER%22%7D%5D%7D

#
#POST /view/8.5/job/iwd_8.5.000-REVIEW/build/api/json HTTP/1.1
#Host: pl-byd-srv01.emea.int.genesyslab.com:18080
#Cache-Control: no-cache
#Content-Type: application/x-www-form-urlencoded
#
#json=%7B%22parameter%22%3A%5B%7B%22name%22%3A%22BRANCH%22%2C%22value%22%3A%22MASTER%22%7D%5D%7D
#from models import Review, Build
#from models import Review
import config


app = Flask(__name__)
app.config.from_object("config")
db = SQLAlchemy(app)



class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    owner = db.Column(db.String(50))
    owner_email = db.Column(db.String(120))
    created_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    title = db.Column(db.String(120))
    sha1 = db.Column(db.String(40), index=True)
    bookmark = db.Column(db.String(120))
    builds = db.relationship("Build")
    inspections = db.relationship("CodeInspection")

    def __init__(self, owner=None, owner_email=None, title=None, sha1=None, bookmark=None):
        self.owner = owner
        self.owner_email = owner_email
        self.title = title
        self.sha1 = sha1
        self.bookmark = bookmark


class Build(db.Model):
    __tablename__ = 'builds'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id'))
    build_number = db.Column(db.Integer)
    build_url = db.Column(db.String(120))
    status = db.Column(db.String(20))
    job_name = db.Column(db.String(30))
    scheduled = db.Column(db.String(30))

    def __init__(self, review_id = None, build_no = None, build_url = None, status = None, job_name = None):
        self.review_id = review_id
        self.build_number = build_no
        self.build_url = build_url
        self.status = status
        self.job_name = job_name



class CodeInspection(db.Model):
    __tablename__ = 'inspections'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id'))
    inspection_number = db.Column(db.Integer)
    inspection_url = db.Column(db.String(120))
    status = db.Column(db.String(20))

    def __init__(self, review_id = None, inspection_number = None, inspection_url = None, status = None):
        self.review_id = review_id
        self.inspection_number = inspection_number
        self.inspection_url = inspection_url
        self.status = status



#db.drop_all()
db.create_all()

currDir = os.path.dirname(__file__)
repo = Repo2(os.path.join(currDir, "repo"))
productBranches = ["default", "master", "iwd-8.1.000", "iwd-8.1.001", "iwd-8.1.101", "iwd-8.0.001", "iwd-8.0.002", "iwd-8.0.003"]

jenkins = Jenkins("http://pl-byd-srv01.emea.int.genesyslab.com:18080")


#Build.query.filter(Build.review_id == 1).all()
#res = Review.query.filter(Review.id == 1).first()
#print dir(res.builds)
#res.builds.append(Build(None, "111", "sssss"))
#db_session.add(res)
#db_session.commit()
#init_db()

#u = User('admin', 'admin@localhost')
#db_session.add(u)
#db_session.commit()

@app.route('/')
def index():
    return redirect(url_for('changes_new'))


@app.route('/changes/new')
def changes_new():
    #branches = repo.get_branch_names()
    #heads = repo.hg_heads()
    #bookmarks=repo.hg_bookbarks()
    #branches.remove("default") if "default" in branches else ""
    #branches=branches+bookmarks
    heads = repo.hg_heads()
    for h in heads:
        h['src'] = h['bookmarks']
        sha1 = repo.hg_log(identifier=h['rev'], template="{node}")
        count = Review.query.filter(Review.sha1 == sha1).count()
        if (count < 1):
            review = Review("dummy user", "dummy@email.com", h["desc"], sha1, h["bookmarks"])
            db.session.add(review)
            db.session.commit()
    return render_template('changes.html', type="New", heads=heads, productBranches=productBranches)


@app.route('/changes/latest')
def changes_latest():
    return changes_latest_in_branch("default")


@app.route('/changes/latest/<branch>')
def changes_latest_in_branch(branch):
    log = repo.hg_log(branch=branch, limit=30)
    return render_template('log.html', log=log, branch=branch)


@app.route('/merge/<bookmark>')
def merge_with_default(bookmark):
    return merge_branch(bookmark, "default")


@app.route('/inspect',  methods=['POST'])
def inspect_diff():
    info=repo.hg_head_changeset_info(request.form['changeset'])
    rev=info["rev"]
    cc = CodeCollaborator()
    ccInspectionId=cc.create_empty_cc_review()
    res, output = cc.upload_diff(ccInspectionId, rev, repo.path)
    if (res):
        review = Review.query.filter(Review.sha1 == request.form['changeset']).first()
        inspection = CodeInspection()
        inspection.inspection_number = ccInspectionId
        inspection.inspection_url = config.CC_REVIEW_URL.format(reviewId=ccInspectionId)
        inspection.review_id = review.id
        inspection.status = 'NEW'
        db.session.add(inspection)
        db.session.commit()
        message="CodeCollaborator review #{reviewId} has been created. View: {url}".format(reviewId=ccInspectionId, url=inspection.inspection_url)
    else:
        message="There was an error creating CodeCollaborator review. \n\n" + output
    return redirect(url_for('changeset_info', changeset=request.form['changeset']))



@app.route('/merge', methods=['POST'])
def merge_from_post():
    return merge_branch(request.form['src'], request.form['dst'])


@app.route('/build', methods=['POST'])
def jenkins_build():
    build_info = jenkins.run_job(config.REVIEW_JOB_NAME, request.form['src'])
    if build_info is not None:
        info = repo.hg_head_bookmark_info(request.form['src'])
        review = Review.query.filter(Review.sha1 == info['changeset']).first()
        build = Build(review.id, build_info["buildNo"], build_info["url"], None, config.REVIEW_JOB_NAME)
        db.session.add(build)
        db.session.commit()
    return redirect(url_for('changeset_info', changeset=info["changeset"]))


@app.route('/info/<changeset>')
def changeset_info(changeset):
    update_build_status()
    reviews = Review.query.filter(Review.sha1 == changeset).all()
    return render_template("info.html", reviews=reviews, productBranches=productBranches)

@app.route('/merge/<src>/<dst>')
def merge_branch(src, dst):
    msg = ""
    e = ""
    diff = ""
    try:
        diff = repo.hg_log(branch=src)
        repo.hg_update(src)
        bookmarks = repo.hg_bookbarks(True)
        heads = repo.hg_heads()
        res3 = repo.hg_update(dst)
        res4 = repo.hg_merge(src)
        for h in heads:
            if h["bookmarks"] == src:
                title = h['desc']
        res5 = repo.hg_commit("Merge '{desc}' ({src}) with {dst}".format(src=src, dst=dst, desc=title), user="me")
        if src in bookmarks:
            res6 = repo.hg_bookmark(src, delete=True)
        msg = "'{desc}' in bookmark '{src}' was successfully merged with '{dst}. <br/>Changes: <br><pre>{diff}</pre>'".format(src=src, dst=dst, diff=diff, desc=title)
    except HgException, e:
        print "===" + str(e)
    return render_template('changes.html', type="Merging", exception=e, message=msg, diff=diff)
    #return render_template('changes.html', type="Merging", src=src, dst=dst)



def update_build_status():
    builds = Build.query.filter(or_(Build.status != "SUCCESS", Build.status == None)).all()
    for b in builds:
       build_info = jenkins.get_build_info(b.job_name, b.build_number)
       b.status =  build_info["result"]
       b.scheduled = build_info["id"]
       db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0')



