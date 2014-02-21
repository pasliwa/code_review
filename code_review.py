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
import sqlalchemy
from sqlalchemy.sql.expression import or_, desc, asc, and_
from flask import Flask, redirect, url_for, flash
from flask.globals import request
from flask.templating import render_template
import re
from ext.CodeCollaborator import CodeCollaborator
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
from flask_mail import Mail, Message
from math import ceil
from flask_wtf import Form
from wtforms import TextField
from wtforms.validators import DataRequired, Optional, Email



app = Flask(__name__)
app.config.from_object("configDev")
db = SQLAlchemy(app)




class SearchForm(Form):
    title = TextField('title', description="title", validators=[Optional()])
    author = TextField('author', description="author", validators=[Optional()])


class Pagination(object):
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count
    @property
    def pages(self):
        return int(ceil(self.total_count / float(self.per_page)))
    @property
    def has_prev(self):
        return self.page > 1
    @property
    def has_next(self):
        return self.page < self.pages
    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        last = 0
        for num in xrange(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and \
                num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num



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

def url_for_other_page(page):
    #args = request.view_args.copy()
    args = dict(request.view_args.items() + request.args.to_dict().items())
    args['page'] = page
    return url_for(request.endpoint, **args)
app.jinja_env.globals['url_for_other_page'] = url_for_other_page


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


repo = Repo2(app.config["REPO_PATH"])
jenkins = Jenkins(app.config["JENKINS_URL"])





@app.route('/')
def index():
    return redirect(url_for('changes_new'))


@app.route('/changes/new', methods=['GET', 'POST'], defaults={'page': 1})
@app.route('/changes/new/<int:page>')
@login_required
#@roles_required('admin')
def changes_new(page):
    form = SearchForm()
    f = Review.query.filter(Review.status == "OPEN")
    author = request.args.get('author', None)
    title = request.args.get('title', None)
    if author:
       f = f.filter((Review.owner.contains(author)))
    if title:
       f = f.filter((Review.title.contains(title)))
    query = f.order_by(desc(Review.created_date)).paginate(page, app.config["PER_PAGE"], False)
    total = query.total
    reviews = query.items
    pagination = Pagination(page, app.config["PER_PAGE"], total)
    return render_template('changes.html', type="New", reviews=reviews, productBranches=app.config["PRODUCT_BRANCHES"], form=form, pagination=pagination)


@app.route('/changes/merged', methods=['GET', 'POST'], defaults={'page': 1})
@app.route('/changes/merged/<int:page>')
def changes_merged(page):
    form = SearchForm()
    f = Review.query.filter(Review.status == "MERGED")
    author = request.args.get('author', None)
    title = request.args.get('title', None)
    if author:
       f = f.filter((Review.owner.contains(author)))
    if title:
       f = f.filter((Review.title.contains(title)))
    query = f.order_by(desc(Review.created_date)).paginate(page, app.config["PER_PAGE"], False)
    total = query.total
    reviews = query.items
    pagination = Pagination(page, app.config["PER_PAGE"], total)
    return render_template('changes.html', type="Merged", reviews=reviews, form=form, pagination=pagination, mode="merged")


@app.route('/inspect',  methods=['POST'])
@login_required
@roles_required('user')
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
    flash("Code Collaborator review has been scheduled for processing", "notice")
    return redirect(url_for('changeset_info', review=request.form['back_id']))



@app.route('/build', methods=['POST'])
@login_required
@roles_required('user')
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
    flash("Jenkins build has been scheduled for processing", "notice")
    return redirect(url_for('changeset_info', review=request.form['back_id']))


@app.route('/info/<review>', methods=['POST', 'GET'])
def changeset_info(review):
    review = Review.query.filter(Review.id == review).first()
    if request.method == 'POST':
        review.target = request.form['target']
        db.session.add(review)
        db.session.commit()
        flash("Target branch has been set to <b>{b}</b>".format(b=review.target), "notice")
    for c in review.changesets:
        update_build_status(c.id)
    return render_template("info.html", review=review, productBranches=app.config["PRODUCT_BRANCHES"])




@app.route('/merge', methods=['POST'])
@login_required
@roles_required('admin')
def merge_branch():
    sha1 = request.form['sha1']
    changeset = Changeset.query.filter(Changeset.sha1 == sha1).first()
    review = Review.query.filter(Review.id == changeset.review_id).first()

    if (review.target == "iwd-8.5.000"):
        bookmark = "master"
    else:
        bookmark = review.target

    link = url_for("changeset_info", review=review.id, _external=True)

    repo_sync()

    app.logger.info("Merging {sha1} into {target}".format(sha1 = sha1, target = review.target))
    repo.hg_update(bookmark)

    try:
        output = repo.hg_merge(sha1)
    except HgException as e:
        output = str(e)

    app.logger.info("Merge result: {output}".format(output=output))

    error = False
    subject = "Successful merge '{name}' with {dest}".format(name=review.title, sha1=changeset.sha1, dest=review.target)

    if "abort: nothing to merge" in output:
        result = repo.hg_bookmark_move(sha1, bookmark)
        app.logger.info(result)
        flash("Changeset has been merged", "notice")
    elif "use 'hg resolve' to retry unresolved" in output:
        result = repo.hg_update(bookmark, clean=True)
        app.logger.info(result)
        flash("There is merge conflict: <br/><pre>" + result + "</pre>", "error")
        subject = "Merge conflict - can't merge '{name}' with {dest}".format(name=review.title, sha1=changeset.sha1, dest=review.target)
        error = True
    elif "abort: merging with a working directory ancestor has no effect" in output:
        result = repo.hg_bookmark_move(sha1, bookmark)
        app.logger.info(result)
        flash("Changeset has been merged", "notice")

    html = subject + "<br/><br/>Review link: <a href=\"{link}\">{link}</a><br/>Owner: {owner}<br/>SHA1: {sha1} ".format(link=link, sha1=changeset.sha1, owner=changeset.owner)

    recpts = get_admin_emails()
    recpts.append(changeset.owner_email)
    recpts = list(set(recpts))

    msg = Message(subject,
                  sender=app.config["SECURITY_EMAIL_SENDER"],
                  recipients=recpts)
    msg.html = html
    mail.send(msg)

    if not error:
        review.status = "MERGED"
        review.close_date = datetime.datetime.utcnow()
        db.session.add(review)
        db.session.commit()
        flash("Review has been closed", "notice")

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
    role = user_datastore.find_role("user")
    user_datastore.add_role_to_user(user, role)

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


@app.route('/repo_scan')
def repo_scan():

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
    return redirect(url_for('changes_new'))


#@login_required
#@roles_required('admin')
@app.route('/init_users')
def init_users():
    admin_role = user_datastore.find_or_create_role(name="admin", description="Administrator")
    user_role = user_datastore.find_or_create_role(name="user", description="User");
    admin = user_datastore.create_user(email="roman.szalla@genesyslab.com", password=encrypt_password("password"), cc_login = "roman.szalla")
    user_datastore.add_role_to_user(admin, admin_role)
    user_datastore.add_role_to_user(admin, user_role)
    admin = user_datastore.create_user(email="maciej.malycha@genesyslab.com", password=encrypt_password("password"), cc_login = "maciej")
    user_datastore.add_role_to_user(admin, admin_role)
    user_datastore.add_role_to_user(admin, user_role)
    flash("Users have been populated", "notice")
    return redirect(url_for('changes_new'))




@app.context_processor
def inject_user():
    return dict(user=current_user)

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(error)
    return "500 error. Administrator has been notified about this error." , 500


def get_admin_emails():
    admins =  []
    adms = User.query.join(User.roles).filter(Role.name == "admin").all()
    for a in adms:
        admins.append(a.email)
    return admins


if __name__ == '__main__':


    db.create_all()
    db.session.commit()


    ADMINS = get_admin_emails()

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




