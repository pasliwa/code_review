import logging
import datetime
import re
from itertools import chain

from flask import render_template, flash, redirect, url_for
# noinspection PyUnresolvedReferences
from flask.ext.login import current_user
# noinspection PyUnresolvedReferences
from flask.ext.mail import Message
from flask.globals import request
# noinspection PyUnresolvedReferences
from flask.ext.security import login_required, roles_required, user_registered
from sqlalchemy.sql.expression import and_

from app import app, db, repo, jenkins, cc, mail, user_datastore
from app.hgapi.hgapi import HgException
from app.model import Build, Changeset, CodeInspection, Review, Diff
from app.view import Pagination
from app.utils import update_build_status, \
    get_admin_emails, get_reviews, get_new, get_reworks, el
from app.perfutils import performance_monitor
from view import SearchForm


logger = logging.getLogger(__name__)


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
@performance_monitor("Request /changes/new")
def changes_new():
    logger.info("Requested URL /changes/new")
    repo.hg_sync()

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
            repo.hg_close_branch(request.form['sha1'])
            return redirect(url_for('changes_new'))

    revisions = get_new(repo)
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
    return render_template('active.html', reviews=data["r"],
                           form=form, pagination=data["p"])


@app.route('/changes/merged', methods=['GET', 'POST'], defaults={'page': 1})
@app.route('/changes/merged/<int:page>')
def changes_merged(page):
    form = SearchForm()
    data = get_reviews("MERGED", page, request)
    return render_template('merged.html', reviews=data["r"], form=form, pagination=data["p"])


@app.route('/changeset/<int:cs_id>/inspect', methods=['POST'])
@login_required
@roles_required('user')
def inspect_diff(cs_id):
    cs = Changeset.query.filter(Changeset.id == cs_id).first()
    if cs is None:
        logger.error("Changeset not found: %d", cs_id)
        return redirect(url_for('index'))
    redirect_url = redirect(url_for('changeset_info', sha1=cs.sha1))
    if not cs.is_active():
        logger.error("Cannot schedule inspection. Changeset %d is not active "
                     "within review %d. Active changeset is %d",
                     cs.id, cs.review.id, cs.review.active_changeset().id)
        flash("Changeset is not active. Cannot schedule inspection.", "error")
        return redirect_url
    if cs.review.inspection is None:
        if cs.review.target is None:
            logger.error("Cannot schedule inspection. Review %d has no target",
                         cs.review.id)
            flash("Review has no target release. Cannot schedule inspection",
                  "error")
            return redirect_url
        msg = "Code Inspection is scheduled for processing"
        ci = CodeInspection(current_user.cc_login, cs.review)
        db.session.add(ci)
        logger.info("CodeInspection record %d has been created for review %d",
                    ci.id, cs.review.id)
    else:
        msg = "Rework is scheduled for upload to CodeCollaborator"
    if cs.diff is not None:
        logger.error("Cannot upload diff for changeset %d. Already exists "
                     "diff %d", cs.id, cs.diff.id)
        flash("Rework has been already scheduled for upload", "error")
        return redirect_url
    root = repo.hg_ancestor(cs.sha1, cs.review.target)
    diff = Diff(cs, root)
    db.session.add(diff)
    logger.info("Diff record %d has been created for changeset %d",
                diff.id, cs.id)
    db.session.commit()

    flash(msg, "notice")
    return redirect_url


@app.route('/build', methods=['POST'])
@login_required
@roles_required('user')
def jenkins_build():
    info = repo.revision(request.form['src'])
    changeset = Changeset.query.filter(Changeset.sha1 == info.node).first()
    build = Build(changeset_id=changeset.id, status="SCHEDULED",
                  job_name=request.form['release'] + "-ci")
    db.session.add(build)
    db.session.commit()
    logger.info("Jenkins build for changeset id " + str(changeset.id) +
                " has been added to queue. Changeset: " + str(changeset) +
                " , build: " + str(build))
    flash("Jenkins build has been scheduled for processing", "notice")
    return redirect(url_for('changeset_info', sha1=request.form['back_id']))


@app.route('/changeset/<sha1>', methods=['POST', 'GET'])
@performance_monitor("Request /changeset/<sha1>")
def changeset_info(sha1):
    logger.info("Requested URL /changeset/%s", sha1)
    cs = Changeset.query.filter(Changeset.sha1 == sha1).first()
    #TODO: What if changeset doesn't exist?
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



@app.route('/review/<int:review>', methods=['POST', 'GET'])
@performance_monitor("Request /review/<int:review>")
def review_info(review):
    logger.info("Requested URL /review/%d", review)
    review = Review.query.filter(Review.id == review).first()
    if review.status == "ACTIVE":
        repo.hg_sync()
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
        #TODO: If inspection scheduled, target cannot change
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
        #TODO: If inspection scheduled, cannot abandon changeset
        #TODO: Only active changeset or its descendant can be abandoned
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
            repo.hg_close_branch(request.form["sha1"])
            flash("Changeset '{title}' (SHA1: {sha1}) has been abandoned".format(title=changeset.title,
                                                                                 sha1=changeset.sha1), "notice")

    if review.status == "ACTIVE":
        for c in review.changesets:
            update_build_status(c.id)

    return render_template("review.html", review=review,
                           descendants=get_reworks(repo, review))


@app.route('/merge', methods=['POST'])
@login_required
@roles_required('admin')
@performance_monitor("Request /merge")
def merge_branch():
    sha1 = request.form['sha1']
    logger.info("Requested URL /merge for sha1=%s", sha1)
    changeset = Changeset.query.filter(Changeset.sha1 == sha1).first()
    review = Review.query.filter(Review.id == changeset.review_id).first()
    bookmark = review.target

    link = url_for("review_info", review=review.id, _external=True)

    repo.hg_sync()

    logger.info("Merging %s into %s", sha1, review.target)
    repo.hg_update(bookmark)

    try:
        output = repo.hg_merge(sha1)
    except HgException as e:
        output = str(e)

    logger.info("Merge result: {output}".format(output=output))

    error = False
    subject = "Successful merge '{name}' with {dest}".format(name=review.title, sha1=changeset.sha1, dest=review.target)

    if "abort: nothing to merge" in output:
        repo.hg_update(sha1)
        result = repo.hg_bookmark(bookmark, force=True)
        logger.info(result)
        flash("Changeset has been merged", "notice")
    elif "use 'hg resolve' to retry unresolved" in output:
        repo.hg_update("null", clean=True)
        flash("There is merge conflict. Merge with bookmark " + bookmark +
              " and try again.", "error")
        subject = "Merge conflict - can't merge '{name}' with {dest}".format(name=review.title, sha1=changeset.sha1,
                                                                             dest=review.target)
        error = True
    elif "abort: merging with a working directory ancestor has no effect" in output:
        repo.hg_update(sha1)
        result = repo.hg_bookmark(bookmark, force=True)
        logger.info(result)
        flash("Changeset has been merged", "notice")
    else:
        repo.hg_commit("Merged with {target}".format(target=review.target))
        repo.hg_update("null")

    try:
        repo.hg_push()
    except HgException, ex:
        if not "no changes found" in ex.message:
            raise

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


@app.route('/changelog/<start>/<stop>')
@login_required
@roles_required('admin')
def changelog(start, stop):
    repo.hg_sync()
    rev_start = repo.revision(start)
    rev_stop = repo.revision(stop)

    rev_list = {}
    for rev in repo.revisions([1, rev_stop.node]):
        rev_list[rev.node] = rev
    for rev in repo.revisions([1, rev_start.node]):
        rev_list.pop(rev.node, None)

    jira_re = re.compile("(IWD-\d+)|(EVO-\d+)|(IAP-\d+)", re.IGNORECASE)
    jira_list = {}
    for node, rev in rev_list.items():
        tickets = set(chain(*jira_re.findall(rev.desc))) - set([''])
        for ticket in tickets:
            if ticket not in jira_list:
                jira_list[ticket] = ''
            jira_list[ticket] += '\n' + rev.desc

    return render_template("log.html", start=start, stop=stop, jira_list=sorted(jira_list.items()))


############################################################################
#
#          MAINTENANCE - DEDICATED FOR CRON JOBS
#
############################################################################



@app.route('/run_scheduled_jobs')
def run_scheduled_jobs():
    # CC reviews
    logger.info("Running scheduled jobs")
    inspections = CodeInspection.query.filter(
        CodeInspection.status == "SCHEDULED").all()
    for i in inspections:
        try:
            logger.info("Processing inspection: %d", i.id)
            if i.number is not None:
                logger.error("Inspection %d with number is still scheduled.",
                             i.id)
                continue
            i.number, i.url = cc.create_review(i.review.title, i.review.target)
            if i.number is None:
                logger.error("Creating inspection %d in CodeCollaborator "
                             "failed.", i.id)
                continue
            cc.add_participant(i.number, i.author, "author")
            i.status = "NEW"
            #TODO: What happens if there is exception in database? Thousands of inspections will be created?
            db.session.commit()
        except:
            logger.exception("Exception when processing inspection: %d", i.id)
            db.session.rollback()

    # CC diffs
    diffs = Diff.query.filter(Diff.status == "SCHEDULED").all()
    for d in diffs:
        try:
            logger.info("Processing diff: %d", d.id)
            i = d.changeset.review.inspection
            if i.status == "SCHEDULED":
                logger.error("Inspection of diff %d is still scheduled", d.id)
                continue
            if cc.upload_diff(i.number, d.root, d.changeset.sha1):
                d.status = "UPLOADED"
                db.session.commit()
        except:
            logger.exception("Exception when uploading diff: %d", d.id)
            db.session.rollback()

    # Jenkins builds
    builds = Build.query.filter(Build.status == "SCHEDULED").all()
    for b in builds:
        try:
            logger.info("Processing build: %d", b.id)
            build_info = jenkins.run_job(b.job_name, b.changeset.sha1)
            if build_info is None:
                logger.error("Build id " + str(b.id) + " has been skipped.")
                continue
            b.status = build_info["status"]
            b.request_id = build_info["request_id"]
            b.scheduled = build_info["scheduled"]
            b.build_url = build_info["build_url"]
            if "build_number" in build_info:
                b.build_number = build_info["build_number"]
            db.session.commit()
        except:
            logger.exception("Exception when running build: %d", b.id)
            db.session.rollback()

    logger.info("Running scheduled jobs completed")
    return redirect(url_for('index'))


@app.errorhandler(Exception)
def internal_error(ex):
    logger.exception(ex)
    import traceback
    error = {'message': str(ex), 'stacktrace': traceback.format_exc()}
    return render_template('500.html', error=error), 500

