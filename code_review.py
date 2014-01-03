from flask.ext.security.decorators import roles_required
from flask.ext.security.signals import user_registered
from flask.ext.security.utils import encrypt_password
from flask_security.core import current_user
from flask.ext.login import current_user
import os
import datetime
from sqlalchemy.sql.expression import or_, desc
from flask import Flask, redirect, url_for
from flask.globals import request
from flask.templating import render_template
import re
from hgapi import HgException
from Repo2 import Repo2
from flask.ext.sqlalchemy import SQLAlchemy
import subprocess
import json
import requests
import urllib
from uuid import uuid4
import time
from flask.ext.security import Security, SQLAlchemyUserDatastore, UserMixin, RoleMixin, login_required
from flask_mail import Mail

app = Flask(__name__)
app.config.from_object("configDev")
db = SQLAlchemy(app)


if "check_output" not in dir( subprocess ): # duck punch it in!
    def f(*popenargs, **kwargs):
        if 'stdout' in kwargs:
            raise ValueError('stdout argument not allowed, it will be overridden.')
        process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
        output, unused_err = process.communicate()
        retcode = process.poll()
        if retcode:
            cmd = kwargs.get("args")
            if cmd is None:
                cmd = popenargs[0]
            raise subprocess.CalledProcessError(retcode, cmd)
        return output
    subprocess.check_output = f


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
    changesets = db.relationship("Changeset", order_by=desc("created_date"))

    def __init__(self, owner=None, owner_email=None, title=None, sha1=None, bookmark=None, status = None):
        self.owner = owner
        self.owner_email = owner_email
        self.title = title
        self.sha1 = sha1
        self.bookmark = bookmark
        self.status = status


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


class CodeCollaborator(object):
    def create_empty_cc_review(self):
        output = subprocess.check_output(
            "{cc} --no-browser --non-interactive admin review create".format(cc=app.config["CC_BIN"]), shell=True)
        regex = re.compile("Review #([0-9]+)")
        r = regex.search(output)
        reviewId = r.groups()[0]
        return reviewId

    def upload_diff(self, reviewId, revision, repoPath):
        parent = repo.hg_parent(revision)
        # TODO: get parent revision, -1 doesn't work
        output = subprocess.check_output(
            "{cc} addhgdiffs {reviewId} -r {parent} -r {rev}".format(cc=app.config["CC_BIN"], reviewId=reviewId,
                                                                    parent=parent, rev=revision), cwd=repoPath, shell=True)
        if "Changes successfully attached" in output:
            return (True, output)
        return (False, output)



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



class Jenkins(object):
    def __init__(self, url):
        self.url = url


    def get_next_build_number(self, jobName):
        resp = requests.get(self.url + "/job/" + jobName + "/api/python?pretty=true")
        props = eval(resp.content)
        return props["nextBuildNumber"]

    def run_job(self, jobName, rev):
        buildNo = self.get_next_build_number(jobName)
        uuid = str(uuid4())
        info = repo.hg_rev_info(rev)
        sha1 = info["changeset_short"]
        payload = urllib.urlencode({'json': json.dumps({"parameter": [{"name": "BRANCH", "value": sha1}, {"name": "REQUEST_ID", "value": uuid}]})})
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        resp = requests.post(self.url + "/job/" + jobName + "/build/api/json", data=payload, headers=headers)
        if resp.status_code == 201:
            counter = 1;
            while (counter < 10):
                counter = counter + 1
                # Jenkins queues job and does not start them immediately
                # lets give him some time to respond
                time.sleep(counter)
                resp = requests.get(self.url + "/job/" + jobName + "/" + str(buildNo) + "/api/python", data=payload, headers=headers)
                if resp.status_code != 404:
                    # build has started, make sure we got the right build number (possible race-condition)
                    props = eval(resp.content)
                    for a in props['actions']:
                        if a.has_key("parameters"):
                            for parameters in a['parameters']:
                                if parameters['name'] == "REQUEST_ID" and parameters['value'] == uuid:
                                    return {"buildNo": buildNo, "url": props["url"], "result" : None}
                    return None
        else:
            return None


    def get_build_info(self, jobName, buildNo):
        if jobName == None or buildNo == None:
            return None
        resp = requests.get(self.url + "/job/" + jobName + "/" + str(buildNo) + "/api/python?pretty=true")
        props = eval(resp.content)
        return props

    def get_build_result(self, jobName, buildNo):
        res = self.get_build_info(jobName, buildNo)
        return res['result'] if res.has_key("result") else None



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
    active = db.Column(db.Boolean())
    confirmed_at = db.Column(db.DateTime())
    roles = db.relationship('Role', secondary=roles_users,
                            backref=db.backref('users', lazy='dynamic'))


# Setup Flask-Security
user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)

mail = Mail(app)



#db.drop_all()
#db.create_all()

# Create a user to test with
@app.before_first_request
def create_user():
    db.create_all()
    #user_datastore.create_user(email='roman.szalla@genesyslab.com', password='test')
    db.session.commit()




repo = Repo2(app.config["REPO_PATH"])
jenkins = Jenkins(app.config["JENKINS_URL"])





@app.route('/')
def index():
    return redirect(url_for('changes_new'))


@app.route('/changes/new')
#@login_required
#@roles_required('admin')
def changes_new():
    #user = current_user
    #yyy=user.is_anonymous()
    # TODO: reading heads directly from repo is slow, do it periodicaly, save 2 db, present heads from db here
    temp = repo.hg_heads()
    heads = []
    map((lambda x: heads.append(x) if x["bookmarks"] not in app.config["PRODUCT_BRANCHES"] + app.config["IGNORED_BRANCHES"] else x), temp)
    for h in heads:
        h['src'] = h['bookmarks']
        sha1 = repo.hg_log(identifier=h['rev'], template="{node}")

        #make sure changeset is in DB
        count = Changeset.query.filter(Changeset.sha1 == h["changeset"]).count()
        if (count < 1):
            changeset = Changeset(h["author"], h["email"], h["desc"], sha1, h["bookmarks"], "new")
            db.session.add(changeset)
            db.session.commit()

        # try to find valid review for changeset by searching the commit tree 1 levels down
        # TODO improvement - extract to function, possibly make it recursive
        changeset = Changeset.query.filter(Changeset.sha1 == h["changeset"]).first()
        if (changeset.review_id is None):
            parent = repo.hg_rev_info(changeset.sha1)
            rev_parent = parent["rev_parent"]
            # get sha1 for parent revision
            parent_info = repo.hg_rev_info(rev_parent)
            parent_sha1 = parent_info["changeset"]
            # look for review for parent
            parent_changeset = Changeset.query.filter(Changeset.sha1 == parent_sha1).first()
            if (parent_changeset is not None and parent_changeset.review_id is not None):
                parent_review = Review.query.filter(Review.id == parent_changeset.review_id).first()
                if (parent_review.status == "OPEN"):
                    changeset.review_id = parent_review.id
                    db.session.add(changeset)
                    db.session.commit()

        # review for parent has not been found
        if (changeset.review_id is None):
            review = Review(owner=h["author"], owner_email=h["email"], title=h["desc"], sha1=sha1,
                            bookmark=h["bookmarks"], status="OPEN")
            db.session.add(review)
            db.session.commit()
            changeset.review_id = review.id
            db.session.add(changeset)
            db.session.commit()

    reviews = Review.query.filter(Review.status == "OPEN").order_by(desc(Review.created_date)).all()
    return render_template('changes.html', type="New", reviews=reviews, productBranches=app.config["PRODUCT_BRANCHES"])


@app.route('/changes/latest')
def changes_latest():
    return changes_latest_in_branch("default")


@app.route('/changes/merged')
def changes_merged():
    reviews = Review.query.filter(Review.status == "MERGED").order_by(desc(Review.created_date)).limit(50).all()
    return render_template('changes.html', type="Merged", reviews=reviews)



@app.route('/changes/latest/<branch>')
def changes_latest_in_branch(branch):
    log = repo.hg_log(branch=branch, limit=50)
    return render_template('log.html', log=log, branch=branch)


@app.route('/merge/<bookmark>')
def merge_with_default(bookmark):
    return merge_branch(bookmark, "default")


@app.route('/inspect',  methods=['POST'])
def inspect_diff():
    info=repo.hg_rev_info(request.form['src'])
    changeset = Changeset.query.filter(Changeset.sha1 == request.form['src']).first()
    inspection = CodeInspection()
    inspection.status = "SCHEDULED"
    inspection.changeset_id = changeset.id
    inspection.sha1 = info["changeset"]
    db.session.add(inspection)
    db.session.commit()
    return redirect(url_for('changeset_info', review=request.form['back_id']))



@app.route('/merge', methods=['POST'])
def merge_from_post():
    return merge_branch(request.form['src'], request.form['dst'])


@app.route('/build', methods=['POST'])
def jenkins_build():
    #jenkins.schedule_job(config.REVIEW_JOB_NAME, request.form['src'])
    info = repo.hg_rev_info(request.form['src'])
    changeset = Changeset.query.filter(Changeset.sha1 == info['changeset']).first()
    build = Build(changeset_id=changeset.id, status="SCHEDULED")
    db.session.add(build)
    db.session.commit()
    return redirect(url_for('changeset_info', review=request.form['back_id']))


@app.route('/info/<review>')
def changeset_info(review):
    review = Review.query.filter(Review.id == review).first()
    for c in review.changesets:
        update_build_status(c.id)
    return render_template("info.html", review=review, productBranches=app.config["PRODUCT_BRANCHES"])

@app.route('/merge/<src>/<dst>')
def merge_branch(src, dst):
    msg = ""
    e = ""
    try:
        #diff = repo.hg_log(branch=src)
        repo.hg_update(src, clean=True)
        bookmarks = repo.hg_bookbarks(True)
        heads = repo.hg_heads()
        res3 = repo.hg_update(dst)
        res4 = repo.hg_merge(src)
        info = repo.hg_rev_info(src)
        title = info['desc']
        res5 = repo.hg_commit("Merge '{desc}' ({src}) with {dst}".format(src=src, dst=dst, desc=title), user="me")
        if info["bookmarks"] in bookmarks:
            res6 = repo.hg_bookmark(info["bookmarks"], delete=True)
        msg = "'{desc}' in bookmark '{src}' was successfully merged with {dst} ".format(src=src, dst=dst, desc=title)
        # close review
        changeset = Changeset.query.filter(Changeset.revision == src).first()
        review = Review.query.filter(Review.id == changeset.review_id).first()
        review.status = "MERGED"
        review.close_date = datetime.datetime.utcnow()
        db.session.add(review)
        db.session.commit()
    except HgException, e:
        print "===" + str(e)
    return render_template('changes.html', type="Merging", exception=e, message=msg)
    #return render_template('changes.html', type="Merging", src=src, dst=dst)



@app.route('/run_scheduled_jobs')
def run_scheduled_jobs():

    # CC reviews
    inspections = CodeInspection.query.filter(CodeInspection.status == "SCHEDULED").all()
    for i in inspections:
        cc = CodeCollaborator()
        # TODO - investigate how to send rework to CC instead of creating new review
        ccInspectionId=cc.create_empty_cc_review()
        res, output = cc.upload_diff(ccInspectionId, str(i.sha1), repo.path)
        if (res):
            i.inspection_number = ccInspectionId
            i.inspection_url = app.config["CC_REVIEW_URL"].format(reviewId=ccInspectionId)
            i.status = 'NEW'
            db.session.add(i)
            db.session.commit()
            message="CodeCollaborator review #{reviewId} has been created. View: {url}".format(reviewId=ccInspectionId, url=i.inspection_url)
        else:
            message="There was an error creating CodeCollaborator review. \n\n" + output


    # Jenkins builds
    builds = Build.query.filter(Build.status == "SCHEDULED").all()
    for b in builds:
        changeset = Changeset.query.filter(Changeset.id == b.changeset_id).first()
        build_info = jenkins.run_job(app.config["REVIEW_JOB_NAME"], changeset.sha1)
        if build_info is None:
            continue
        b.build_number = build_info["buildNo"]
        b.build_url = build_info["url"]
        b.scheduled = datetime.datetime.utcnow()
        b.status = "RUNNING"
        b.job_name = app.config["REVIEW_JOB_NAME"]
        db.session.add(b)
        db.session.commit()

    return redirect(url_for('index'))


def new_user_registered(sender, **extra):
    user = extra["user"]
    user_datastore.add_role_to_user()
    xxx = 1;

user_registered.connect(new_user_registered, app)


def update_build_status(changeset):
    builds = Build.query.filter(Build.changeset_id == changeset).all()
    for b in builds:
       build_info = jenkins.get_build_info(b.job_name, b.build_number)
       if build_info == None:
           continue
       b.status =  build_info["result"]
       b.scheduled = build_info["id"]
       db.session.add(b)
       db.session.commit()


@app.route('/init_users')
def init_users():
    admin_role = user_datastore.create_role(name="admin", description="Administrator");
    user_role = user_datastore.create_role(name="user", description="User");
    admin = user_datastore.create_user(email="roman.szalla@genesyslab.com", password=encrypt_password("password"))
    user_datastore.add_role_to_user(admin, admin_role)
    admin = user_datastore.create_user(email="maciej.malycha@genesyslab.com", password=encrypt_password("password"))
    user_datastore.add_role_to_user(admin, admin_role)
    db.session.commit()
    return redirect(url_for('changes_new'))



@app.context_processor
def inject_user():
    x=1
    return dict(user=current_user)


if __name__ == '__main__':
    app.run(host=app.config["LISTEN_HOST"], threaded=app.config["ENABLE_THREADS"])



