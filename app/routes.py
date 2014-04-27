from flask import render_template, flash, redirect, url_for
# noinspection PyUnresolvedReferences
from flask.ext.login import current_user
# noinspection PyUnresolvedReferences
from flask.ext.mail import Message
from flask.globals import request
# noinspection PyUnresolvedReferences
from flask.ext.security import login_required, roles_required, user_registered
import re
from sqlalchemy.sql.expression import desc, and_
import datetime

from app import app, db, repo, jenkins, mail, user_datastore
from app.hgapi.hgapi import HgException
from app.model import Build
from app.model import Changeset
from app.collab import CodeCollaborator
from app.model import CodeInspection
from app.view import Pagination
from app.model import Review
from app.utils import update_build_status, find_origin_inspection, \
    get_admin_emails, get_reviews, get_new, get_reworks, el
from view import SearchForm


@app.context_processor
def inject_user():
    return dict(user=current_user)


# noinspection PyUnusedLocal
def new_user_registered(sender, **extra):
    user = extra["user"]
    role = user_datastore.find_role("user")
    user_datastore.add_role_to_user(user, role)


user_registered.connect(new_user_registered, app)

#TODO: Split and redesign routes
#TODO: No JIRA support

@app.route('/')
def index():
    return redirect(url_for('changes_active'))


@app.route('/changes/new', methods=['GET', 'POST'])
@login_required
def changes_new():
    repo_sync()

    if request.method == "POST":
        action = request.form['action']

        if action == "start":
            info = repo.revision(request.form['sha1'])
            #TODO: Multiple bookmarks
            review = Review(owner=info.name, owner_email=info.email,
                            title=info.title, bookmark=el(info.bookmarks),
                            status="ACTIVE")
            targets = repo.hg_targets(info.rev, app.config['PRODUCT_BRANCHES'])
            review.add_targets(targets)
            #TODO: Multiple bookmarks
            changeset = Changeset(info.name, info.email, info.title,
                                  request.form['sha1'], el(info.bookmarks),
                                  "ACTIVE")
            review.changesets.append(changeset)
            db.session.add(review)
            db.session.commit()
            return redirect(url_for('review_info', review=review.id))

        if action == "abandon":
            info = repo.revision(request.form['sha1'])
            #TODO: Multiple bookmarks
            changeset = Changeset(info.name, info.email, info.title,
                                  request.form['sha1'], el(info.bookmarks),
                                  "ABANDONED")
            db.session.add(changeset)
            db.session.commit()
            return redirect(url_for('changes_new'))

    revisions = get_new()
    for revision in revisions:
        revision.targets = repo.hg_targets(revision.node,
                                           app.config["PRODUCT_BRANCHES"])

    pagination = Pagination(1, 1, 1)

    return render_template('new.html', revisions=revisions,
                           pagination=pagination)


@app.route('/changes/active', methods=['GET', 'POST'], defaults={'page': 1})
@app.route('/changes/active/<int:page>')
@login_required
def changes_active(page):
    form = SearchForm()
    data = get_reviews("ACTIVE", page, request)
    return render_template('changes.html', type="active", reviews=data["r"],
                           form=form, pagination=data["p"])


@app.route('/changes/merged', methods=['GET', 'POST'], defaults={'page': 1})
@app.route('/changes/merged/<int:page>')
def changes_merged(page):
    form = SearchForm()
    data = get_reviews("MERGED", page, request)
    return render_template('changes.html', type="merged", reviews=data["r"], form=form, pagination=data["p"])


@app.route('/inspect', methods=['POST'])
@login_required
@roles_required('user')
def inspect_diff():
    info = repo.revision(request.form['src'])
    changeset = Changeset.query.filter(Changeset.sha1 == request.form['src']).first()
    inspection = CodeInspection()
    inspection.status = "SCHEDULED"
    inspection.changeset_id = changeset.id
    inspection.sha1 = info.node
    db.session.add(inspection)
    db.session.commit()
    app.logger.info("Code Collaborator review for changeset id " + str(
        changeset.id) + " has been added to queue. Changeset: " + str(changeset))
    flash("Code Collaborator review has been scheduled for processing", "notice")
    return redirect(url_for('changeset_info', sha1=request.form['back_id']))


#

@app.route('/build', methods=['POST'])
@login_required
@roles_required('user')
def jenkins_build():
    info = repo.revision(request.form['src'])
    changeset = Changeset.query.filter(Changeset.sha1 == info['node']).first()
    build = Build(changeset_id=changeset.id, status="SCHEDULED",
                  job_name=request.form['release'] + "-ci")
    db.session.add(build)
    db.session.commit()
    app.logger.info(
        "Jenkins build for changeset id " + str(changeset.id) + " has been added to queue. Changeset: " + str(
            changeset) + " , build: " + str(build))
    flash("Jenkins build has been scheduled for processing", "notice")
    return redirect(url_for('changeset_info', sha1=request.form['back_id']))


@app.route('/changeset/<sha1>', methods=['POST', 'GET'])
def changeset_info(sha1):
    cs = Changeset.query.filter(Changeset.sha1 == sha1).first()
    prev = Changeset.query.filter(and_(Changeset.created_date < cs.created_date,
                                       Changeset.status == "ACTIVE",
                                       Changeset.review_id == cs.review_id))\
        .order_by(Changeset.created_date).all()
    if prev:
        prev = prev[-1]
    next_ = Changeset.query.filter(and_(Changeset.created_date > cs.created_date,
                                        Changeset.status == "ACTIVE",
                                        Changeset.review_id == cs.review_id))\
        .order_by(Changeset.created_date).first()
    review = Review.query.filter(Review.id == cs.review_id).first()
    update_build_status(cs.id)
    return render_template("changeset.html", review=review, cs=cs, next=next_,
                           prev=prev)



@app.route('/review/<review>', methods=['POST', 'GET'])
def review_info(review):
    repo_sync()
    review = Review.query.filter(Review.id == review).first()
    if request.method == 'POST':
        if request.form["action"] == "rework":
            # make sure cs doesnt exist
            cs = Changeset.query.filter(Changeset.sha1 == request.form["sha1"]).first()
            if cs is None:
                info = repo.revision(request.form["sha1"])
                #TODO: Multiple bookmarks
                cs = Changeset(info.name, info.email, info.title,
                               info.node, el(info.bookmarks),
                               "ACTIVE")
                cs.review_id = review.id
                db.session.add(cs)
                db.session.commit()
                flash(
                    "Changeset '{title}' (SHA1: {sha1}) has been marked as rework".format(title=cs.title, sha1=cs.sha1),
                    "notice")
            else:
                flash("Error - changeset already exists", "error")
        if request.form["action"] == "abandon":
            review.status = "ABANDONED"
            db.session.add(review)
            for c in review.changesets:
                c.status = "ABANDONED"
                db.session.add(c)
            db.session.commit()
            flash("Review has been abandoned", "notice")
        if request.form["action"] == "target":
            try:
                review.set_target(request.form['target'])
            except Exception, ex:
                flash(str(ex), "error")
            else:
                db.session.add(review)
                db.session.commit()
                msg = "Target branch has been set to <b>{0}</b>"
                flash(msg.format(review.target), "notice")
        if request.form["action"] == "abandon_changeset":
            changeset = Changeset.query.filter(Changeset.sha1 == request.form["sha1"]).first()
            if changeset is None:
                info = repo.revision(request.form["sha1"])
                #TODO: Multiple bookmarks
                changeset = Changeset(info.name, info.email,
                                      info.title, info.node,
                                      el(info.bookmarks))
                changeset.review_id = review.id
            changeset.status = "ABANDONED"
            db.session.add(changeset)
            db.session.commit()
            flash("Changeset '{title}' (SHA1: {sha1}) has been abandoned".format(title=changeset.title,
                                                                                 sha1=changeset.sha1), "notice")

    for c in review.changesets:
        update_build_status(c.id)

    return render_template("review.html", review=review,
                           descendants=get_reworks(review))


@app.route('/merge', methods=['POST'])
@login_required
@roles_required('admin')
def merge_branch():
    sha1 = request.form['sha1']
    changeset = Changeset.query.filter(Changeset.sha1 == sha1).first()
    review = Review.query.filter(Review.id == changeset.review_id).first()
    bookmark = review.target

    link = url_for("review_info", review=review.id, _external=True)

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
        repo.hg_update(sha1)
        result = repo.hg_bookmark(bookmark, force=True)
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
        repo.hg_update(sha1)
        result = repo.hg_bookmark(bookmark, force=True)
        app.logger.info(result)
        flash("Changeset has been merged", "notice")

    repo_sync()

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
        if inspection is None or inspection.inspection_number is None:
            cc_inspection_id = cc.create_review(changeset)
            app.logger.debug("Got new CodeCollaborator review id: " + str(cc_inspection_id))
        else:
            cc_inspection_id = inspection.inspection_number
            app.logger.debug("Rework for CC review " + str(cc_inspection_id))

        res, output = cc.upload_diff(cc_inspection_id, str(i.sha1), repo.path)
        if res:
            i.inspection_number = cc_inspection_id
            i.inspection_url = app.config["CC_REVIEW_URL"].format(reviewId=cc_inspection_id)
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
            app.logger.info("Build id " + str(b.id) + " has been skipped.")
            continue
        b.status = build_info["status"]
        b.request_id = build_info["request_id"]
        b.scheduled = build_info["scheduled"]
        b.build_url = build_info["build_url"]
        if "build_number" in build_info:
            b.build_number = build_info["build_number"]
        db.session.add(b)
        db.session.commit()
        app.logger.info("Build id " + str(b.id) + " has been sent to Jenkins.")

    return redirect(url_for('index'))


#TODO: Move to Mercurial?
#TODO: Check if repo is always reset to bare.
#TODO: Race conditions on repository access
#@login_required
#@roles_required('admin')
@app.route('/repo_sync')
def repo_sync():
    # http://www.kevinberridge.com/2012/05/hg-bookmarks-made-me-sad.html
    app.logger.info("Syncing repos, pull")
    repo.hg_pull()
    bookmarks = repo.hg_bookmarks().keys()
    app.logger.info("Bookmarks: " + str(bookmarks))
    reg_expr = "(?P<bookmark>[\s\w\S]+)@(?P<num>\d+)"
    pattern = re.compile(reg_expr)
    for b in bookmarks:
        match = pattern.search(b)
        if match is not None:
            app.logger.info("Detected a divergent bookmark " + b)
            bookmark = match.group("bookmark")
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
    return redirect(url_for('changes_active'))

@app.errorhandler(Exception)
def internal_error(ex):
    app.logger.exception(ex)
    import traceback
    error = {'message': str(ex), 'stacktrace': traceback.format_exc()}
    return render_template('500.html', error=error), 500

