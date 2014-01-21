from flask.ext.security.decorators import roles_required
from flask.ext.security.signals import user_registered
from flask.ext.security.utils import encrypt_password
from flask_security.core import current_user
from flask.ext.login import current_user
import logging
import logging.handlers
import os
import datetime
from rlcompleter import get_class_members
import shutil
from sqlalchemy.sql.expression import or_, desc, asc
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

    def __str__(self):
        return  str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))





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


class Mapping(db.Model):
    __tablename__ = 'maps'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120))
    value = db.Column(db.String(120))
    type = db.Column(db.String(120))

    def __init__(self, key = None, value = None, type = None):
        self.key = key
        self.value = value
        self.type = type

    def __str__(self):
        return  str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))


class CodeCollaborator(object):

    def create_review(self, changeset):

        review =Review.query.filter(Review.id == changeset.review_id).first()
        target_release = review.target[4:9]

        owner = User.query.filter(User.email == changeset.owner_email).first()
        output = subprocess.check_output("""{cc} --no-browser --non-interactive admin review create \
--creator {owner} \
--custom-field "Overview=Auto generated by code review tool" \
--custom-field "Project=iWD (Intelligent Workload Distribution)" \
--custom-field "Release={rel}" \
--title "{title}"
        """.format(cc=app.config["CC_BIN"], owner=owner.cc_login, title=changeset.title, rel = target_release), shell=True)
        regex = re.compile("Review #([0-9]+)")
        # /home/jenkins/ccollab-client/ccollab --no-browser --non-interactive admin review create --creator piotrr --custom-field "Overview=this is the overview" --custom-field "Project=iWD (Intelligent Workload Distribution)" --title "this is title"
        r = regex.search(output)
        reviewId = r.groups()[0]
        return reviewId

    def create_empty_cc_review(self):
        output = subprocess.check_output(
            "{cc} --no-browser --non-interactive admin review create".format(cc=app.config["CC_BIN"]), shell=True)
        regex = re.compile("Review #([0-9]+)")
        # /home/jenkins/ccollab-client/ccollab --no-browser --non-interactive admin review create --creator piotrr --custom-field "Overview=this is the overview" --custom-field "Project=iWD (Intelligent Workload Distribution)" --title "this is title"
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

    def __str__(self):
        return  str(dict((name, getattr(self, name)) for name in dir(self) if not name.startswith('_')))


class Jenkins(object):
    def __init__(self, url):
        self.url = url


    def get_next_build_number(self, jobName):
        resp = requests.get(self.url + "/job/" + jobName + "/api/python?pretty=true")
        props = eval(resp.content)
        app.logger.debug("Next build number for " + jobName + " is " + str(props["nextBuildNumber"]))
        return props["nextBuildNumber"]

    def run_job(self, jobName, rev):
        buildNo = self.get_next_build_number(jobName)
        uuid = str(uuid4())
        info = repo.hg_rev_info(rev)
        sha1 = info["changeset_short"]
        payload = urllib.urlencode({
            'json': json.dumps(
                {"parameter": [{"name": "BRANCH", "value": sha1}, {"name": "REQUEST_ID", "value": uuid}]})})
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        resp = requests.post(self.url + "/job/" + jobName + "/build/api/json", data=payload, headers=headers)
        app.logger.debug(
            "Scheduling Jenkins job for " + jobName + " using revision " + rev + " Expected build number is " + str(buildNo))
        if resp.status_code == 201:
            counter = 1;
            while (counter < 10):
                counter = counter + 1
                # Jenkins queues job and does not start them immediately
                # lets give him some time to respond
                time.sleep(counter)
                resp = requests.get(self.url + "/job/" + jobName + "/" + str(buildNo) + "/api/python", data=payload,
                                    headers=headers)
                if resp.status_code != 404:
                    # build has started, make sure we got the right build number (possible race-condition)
                    props = eval(resp.content)
                    for a in props['actions']:
                        if a.has_key("parameters"):
                            for parameters in a['parameters']:
                                if parameters['name'] == "REQUEST_ID" and parameters['value'] == uuid:
                                    app.logger.info(
                                        "Successfully scheduled Jenkins job for " + jobName + " using revision " + rev + " url: " +
                                        props["url"])
                                    return {"buildNo": buildNo, "url": props["url"], "result": None}
                    app.logger.error(
                        "Failed job verification, possible race-condition occured. REQUEST_ID: " + uuid + " jobname: " + jobName + " rev: " + rev + " expected build number: " + str(buildNo))
                    return None
        else:
            app.logger.error(
                "There was an error scheduling Jenkins job for " + jobName + " using revision " + rev + " Response status code: " + resp.status_code + " , resp content: " + resp.content)
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
    cc_login = db.Column(db.String(50))
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

    #repo_clone("http://pl-byd-srv01.emea.int.genesyslab.com/hg/iwd8/")

    #user = current_user
    #yyy=user.is_anonymous()
    # TODO: reading heads directly from repo is slow, do it periodicaly, save 2 db, present heads from db here
    temp = repo.hg_heads()
    heads = []
    map((lambda x: heads.append(x) if x["bookmarks"] not in app.config["IGNORED_BRANCHES"] else x), temp)
    for h in heads:
        h['src'] = h['bookmarks']
        sha1 = repo.hg_log(identifier=h['rev'], template="{node}")

        #make sure changeset is in DB
        count = Changeset.query.filter(Changeset.sha1 == h["changeset"]).count()
        if (count < 1):
            changeset = Changeset(h["author"], h["email"], h["desc"], sha1, h["bookmarks"], "new")
            db.session.add(changeset)
            db.session.commit()
            app.logger.info("Added new changeset: " + str(changeset))

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
                    app.logger.info(
                        "Attaching review id " + str(parent_review.id) + " to changeset id " + str(changeset.id) + " found by parent")
                    app.logger.debug("review: " + str(parent_review) + ", changeset: " + str(changeset))
                    db.session.add(changeset)
                    db.session.commit()

        # review for parent has not been found
        if (changeset.review_id is None):
            review = Review(owner=h["author"], owner_email=h["email"], title=h["desc"], sha1=sha1,
                            bookmark=h["bookmarks"], status="OPEN", target="iwd-8.5.000")
            db.session.add(review)
            db.session.commit()
            changeset.review_id = review.id
            db.session.add(changeset)
            db.session.commit()
            app.logger.info("Created new review for changeset id:" + str(changeset.id) + ", review: " + str(review))

        app.logger.info(changeset)

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


#@login_required
#@roles_required('user')
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
    app.logger.info("Code Collaborator review for changeset id " + str(changeset.id) + " has been added to queue. Changeset: " + str(changeset))
    return redirect(url_for('changeset_info', review=request.form['back_id']))



#@login_required
#@roles_required('user')
@app.route('/build', methods=['POST'])
def jenkins_build():
    #jenkins.schedule_job(config.REVIEW_JOB_NAME, request.form['src'])
    info = repo.hg_rev_info(request.form['src'])
    changeset = Changeset.query.filter(Changeset.sha1 == info['changeset']).first()
    build = Build(changeset_id=changeset.id, status="SCHEDULED", job_name=request.form['release'] + "-REVIEW")
    db.session.add(build)
    db.session.commit()
    app.logger.info(
        "Jenkins build for changeset id " + str(changeset.id) + " has been added to queue. Changeset: " + str(
            changeset) + " , build: " + str(build))
    return redirect(url_for('changeset_info', review=request.form['back_id']))


@app.route('/info/<review>', methods=['POST', 'GET'])
def changeset_info(review):
    review = Review.query.filter(Review.id == review).first()
    if request.method == 'POST':
        review.target = request.form['target']
        db.session.add(review)
        db.session.commit()
    for c in review.changesets:
        update_build_status(c.id)
    return render_template("info.html", review=review, productBranches=app.config["PRODUCT_BRANCHES"])



#@login_required
#@roles_required('admin')
@app.route('/merge', methods=['POST'])
def merge_branch():
    sha1 = request.form['sha1']
    changeset = Changeset.query.filter(Changeset.sha1 == sha1).first()
    review = Review.query.filter(Review.id == changeset.review_id).first()

    if (review.target == "iwd-8.5.000"):
        bookmark = "master"
    else:
        bookmark = review.target

    repo_sync()

    app.logger.info("Merging {sha1} into {target}".format(sha1 = sha1, target = review.target))
    repo.hg_update(bookmark)

    try:
        output = repo.hg_merge(sha1)
    except HgException as e:
        output = str(e)

    app.logger.info("Merge result: {output}".format(output=output))

    error = False

    if "abort: nothing to merge" in output:
        result = repo.hg_bookmark_move(sha1, bookmark)
        app.logger.info(result)
    elif "use 'hg resolve' to retry unresolved" in output:
        result = repo.hg_update(bookmark, clean=True)
        app.logger.info(result)
        # TODO - send mail that there is conflict
        error = True
    elif "abort: merging with a working directory ancestor has no effect" in output:
        result = repo.hg_bookmark_move(sha1, bookmark)
        app.logger.info(result)

    # TODO - mail admins on every commit
    # TODO - mail owner with merge result

    if not error:
        review.status = "MERGED"
        review.close_date = datetime.datetime.utcnow()
        db.session.add(review)
        db.session.commit()

    return redirect(url_for('index'))


@app.route('/run_scheduled_jobs')
def run_scheduled_jobs():
    # TODO : add support for flashing messages
    # CC reviews
    inspections = CodeInspection.query.filter(CodeInspection.status == "SCHEDULED").all()
    app.logger.debug("Code Collaborator reviews to be sent to CC server : " + str(inspections))
    for i in inspections:
        app.logger.debug("Processing inspection: " + str(i))
        cc = CodeCollaborator()
        changeset = Changeset.query.filter(Changeset.id == i.changeset_id).first()

        # check if this is a rework
        inspection = find_origin_inspection(changeset)
        if inspection == None or inspection.inspection_number == None:
            ccInspectionId = cc.create_review(changeset)
            app.logger.debug("Got new CodeCollaborator review id: " + str(ccInspectionId))
        else:
            ccInspectionId = inspection.inspection_number
            app.logger.debug("Rework for CC review " + str(ccInspectionId))


        res, output = cc.upload_diff(ccInspectionId, str(i.sha1), repo.path)
        if (res):
            i.inspection_number = ccInspectionId
            i.inspection_url = app.config["CC_REVIEW_URL"].format(reviewId=ccInspectionId)
            i.status = 'NEW'
            db.session.add(i)
            db.session.commit()
            app.logger.info("New CC review has been created: " + str(i))
        else:
            app.logger.error("There was an error creating CodeCollaborator review, inspection: " + str(i) + " , command output: " + output)


    # Jenkins builds
    builds = Build.query.filter(Build.status == "SCHEDULED").all()
    app.logger.debug("Builds to be sent to Jenkins: " + str(builds))
    for b in builds:
        changeset = Changeset.query.filter(Changeset.id == b.changeset_id).first()
        build_info = jenkins.run_job(b.job_name, changeset.sha1)
        if build_info is None:
            app.logger.error("Unable to submit scheduled Jenkins job. Name: " + app.config["REVIEW_JOB_NAME"] + " , changeset: " + str(changeset))
            continue
        b.build_number = build_info["buildNo"]
        b.build_url = build_info["url"]
        b.scheduled = datetime.datetime.utcnow()
        b.status = "RUNNING"
        #b.job_name = app.config["REVIEW_JOB_NAME"]
        db.session.add(b)
        db.session.commit()
        app.logger.info("Build id " + str(b.id) + " has been sent to Jenkins.")

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
       if build_info["building"] == True:
           b.status = "RUNNING"
       b.scheduled = build_info["id"]
       db.session.add(b)
       db.session.commit()


def find_origin_inspection(changeset):
    review = Review.query.filter(Review.id == changeset.review_id).first()
    changesets = review.changesets
    ids = []
    map((lambda x: ids.append(x.id) if x.id else x), changesets)
    inspection = CodeInspection.query.filter(CodeInspection.changeset_id.in_(ids)).order_by(asc(CodeInspection.id)).first()
    return inspection


def repo_clone(url):
    path = app.config["REPO_PATH"]
    if os.path.exists(path):
        shutil.rmtree(path)
    os.mkdir(path)
    repo.hg_clone(url, path)
    repo.hg_update("null", True)




#@login_required
#@roles_required('admin')
@app.route('/init_users')
def init_users():
    admin_role = user_datastore.create_role(name="admin", description="Administrator")
    user_role = user_datastore.create_role(name="user", description="User");
    admin = user_datastore.create_user(email="roman.szalla@genesyslab.com", password=encrypt_password("password"), cc_login = "roman.szalla")
    user_datastore.add_role_to_user(admin, admin_role)
    admin = user_datastore.create_user(email="maciej.malycha@genesyslab.com", password=encrypt_password("password"), cc_login = "maciej")
    user_datastore.add_role_to_user(admin, admin_role)
    db.session.commit()
    return redirect(url_for('changes_new'))



#@login_required
#@roles_required('admin')
@app.route('/init_repo')
def init_repo():
    repo_clone("http://pl-byd-srv01.emea.int.genesyslab.com/hg/iwd8")


#@login_required
#@roles_required('admin')
@app.route('/repo_sync')
def repo_sync():
    # http://www.kevinberridge.com/2012/05/hg-bookmarks-made-me-sad.html
    app.logger.info("Syncing repos, pull")
    repo.hg_pull()
    bookmarks = repo.hg_bookbarks()
    app.logger.info("Bookmarks: "+ str(bookmarks))
    reg_expr = "(?P<bookmark>[\s\w\S]+)@(?P<num>\d+)"
    pattern = re.compile(reg_expr)
    for b in bookmarks:
        match = pattern.search(b)
        if match is not None:
            app.logger.info("Detected a divergent bookmark " + b)
            bookmark = match.group("bookmark")
            bookmark_num = match.group("num")
            # todo - handle merge
            repo.hg_update(bookmark)
            repo.hg_merge(b)
            repo.hg_bookmark(b, delete=True)
            repo.hg_update("null")  #make repo bare again
    app.logger.info("Syncing repos, push")
    try:
        repo.hg_push()
    except HgException as e:
        if "no changes found" in e:
            app.logger.info("No new changes locally so there is nothing to push")
    return redirect(url_for('changes_new'))




@app.context_processor
def inject_user():
    return dict(user=current_user)

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(error)
    return "500 error. Administrator has been notified about this error." , 500


if __name__ == '__main__':
    ADMINS = ['roman.szalla@genesys.com']

    import logging
    from logging.handlers import SMTPHandler, RotatingFileHandler

    mail_handler = SMTPHandler('127.0.0.1',
                               'jenkins@pl-byd-srv01.emea.int.genesyslab.com',
                               ADMINS, 'Code Review  application failed')
    mail_handler.setLevel(logging.ERROR)
    mail_handler.setFormatter(logging.Formatter('''
    Message type:       %(levelname)s
    Location:           %(pathname)s:%(lineno)d
    Module:             %(module)s
    Function:           %(funcName)s
    Time:               %(asctime)s

    Message:

    %(message)s
    '''))
    #app.logger.addHandler(mail_handler)

    here = os.path.dirname(__file__)
    file_handler = RotatingFileHandler(os.path.join(here, "code_review.log"), maxBytes=104857600, backupCount=30)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.DEBUG)

    # don't change this!
    app.logger.setLevel(logging.DEBUG)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(mail_handler)

    app.run(host=app.config["LISTEN_HOST"], threaded=app.config["ENABLE_THREADS"])



