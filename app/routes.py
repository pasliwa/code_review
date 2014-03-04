from flask import render_template, flash, redirect, url_for
from flask.ext.login import current_user
from flask.ext.mail import Message
from flask.globals import request
from flask.ext.security import login_required, roles_required, \
    user_registered
import re
from sqlalchemy.sql.expression import desc
import datetime

from app import app, db, repo, jenkins, mail, user_datastore
from app.hgapi.hgapi import HgException
from app.model import Build
from app.model import Changeset
from app.collab import CodeCollaborator
from app.model import CodeInspection
from app.view import Pagination
from app.model import Review
from app.utils import update_build_status, find_origin_inspection, get_admin_emails, repo_clone
from view import SearchForm


@app.context_processor
def inject_user():
    return dict(user=current_user)


def new_user_registered(sender, **extra):
    user = extra["user"]
    role = user_datastore.find_role("user")
    user_datastore.add_role_to_user(user, role)


user_registered.connect(new_user_registered, app)


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
    return render_template('changes.html', type="new", reviews=reviews, productBranches=app.config["PRODUCT_BRANCHES"],
                           form=form, pagination=pagination)


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
    return render_template('changes.html', type="merged", reviews=reviews, form=form, pagination=pagination)


@app.route('/inspect', methods=['POST'])
@login_required
@roles_required('user')
def inspect_diff():
    info = repo.hg_rev_info(request.form['src'])
    changeset = Changeset.query.filter(Changeset.sha1 == request.form['src']).first()
    inspection = CodeInspection()
    inspection.status = "SCHEDULED"
    inspection.changeset_id = changeset.id
    inspection.sha1 = info["changeset"]
    db.session.add(inspection)
    db.session.commit()
    app.logger.info("Code Collaborator review for changeset id " + str(
        changeset.id) + " has been added to queue. Changeset: " + str(changeset))
    flash("Code Collaborator review has been scheduled for processing", "notice")
    return redirect(url_for('changeset_info', review=request.form['back_id']))


#

@app.route('/build', methods=['POST'])
@login_required
@roles_required('user')
def jenkins_build():
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

    app.logger.info("Merging {sha1} into {target}".format(sha1=sha1, target=review.target))
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
        subject = "Merge conflict - can't merge '{name}' with {dest}".format(name=review.title, sha1=changeset.sha1,
                                                                             dest=review.target)
        error = True
    elif "abort: merging with a working directory ancestor has no effect" in output:
        result = repo.hg_bookmark_move(sha1, bookmark)
        app.logger.info(result)
        flash("Changeset has been merged", "notice")

    html = subject + "<br/><br/>Review link: <a href=\"{link}\">{link}</a><br/>Owner: {owner}<br/>SHA1: {sha1} ".format(
        link=link, sha1=changeset.sha1, owner=changeset.owner)

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


############################################################################
#
#          MAINTENANCE - DEDICATED FOR CRON JOBS
#
############################################################################



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
            app.logger.error("There was an error creating CodeCollaborator review, inspection: " + str(
                i) + " , command output: " + output)


    # Jenkins builds
    builds = Build.query.filter(Build.status == "SCHEDULED").all()
    app.logger.debug("Builds to be sent to Jenkins: " + str(builds))
    for b in builds:
        changeset = Changeset.query.filter(Changeset.id == b.changeset_id).first()
        build_info = jenkins.run_job(b.job_name, changeset.sha1)
        if build_info is None:
            app.logger.error("Unable to submit scheduled Jenkins job. Name: " + b.job_name + " , changeset: " + str(changeset))
            continue
        b.build_number = build_info["buildNo"]
        b.build_url = build_info["url"]
        b.scheduled = datetime.datetime.utcnow()
        b.status = "RUNNING"
        db.session.add(b)
        db.session.commit()
        app.logger.info("Build id " + str(b.id) + " has been sent to Jenkins.")

    return redirect(url_for('index'))


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
                        "Attaching review id " + str(parent_review.id) + " to changeset id " + str(
                            changeset.id) + " found by parent")
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
@app.route('/repo_sync')
def repo_sync():
    # http://www.kevinberridge.com/2012/05/hg-bookmarks-made-me-sad.html
    app.logger.info("Syncing repos, pull")
    repo.hg_pull()
    bookmarks = repo.hg_bookbarks()
    app.logger.info("Bookmarks: " + str(bookmarks))
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


