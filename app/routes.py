import logging
import datetime
import re
from itertools import chain
from urlparse import urlparse, urljoin

from flask import render_template, flash, redirect, url_for
# noinspection PyUnresolvedReferences
from flask.ext.login import current_user
# noinspection PyUnresolvedReferences
from flask.ext.mail import Message
from flask.globals import request
# noinspection PyUnresolvedReferences
from flask.ext.security import login_required, roles_required, user_registered
from sqlalchemy.sql.expression import and_

from app import app, db, repo, jenkins, mail, user_datastore
from app.hgapi.hgapi import HgException
from app.model import Build, Changeset, CodeInspection, Review, Diff, Head
from app.view import Pagination
from app.utils import get_reviews, get_revision_status, get_heads, el
from app.locks import repo_read, repo_write, rework_db_read, rework_db_write
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


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
           ref_url.netloc == test_url.netloc


def refresh_heads():
    repo.hg_sync()
    Head.query.delete()
    for repo_head in get_heads(repo):
        head = Head(repo_head)
        logger.debug("Adding head: %s", head)
        db.session.add(head)
    db.session.commit()


#TODO: Split and redesign routes
#TODO: No JIRA support

# /
# /changes/new              [GET, start, abandon]
# /changes/active
# /changes/active/<page>
# /changes/merged
# /changes/merged/<page>
# /changeset/<id>/inspect   [POST]
# /build                    [POST]
# /changeset/<id>
# /review/<id>              [GET, target, rework, abandon, abandon_changeset]
# /merge

# /review/new/<page>                (/changes/new)
# /review/active/<page>             (/changes/active)
# /review/merged/<page>             (/changes/merged)
# /review/abandoned/<page>
# /review                   [POST]  (/changes/new?action=start)
# /review/<id>
# /review/<id>              [POST]  (/review/<id>?action=rework)
# /review/<id>/abandon      [POST]  (/review/<id>?action=abandon)
# /review/<id>/merge        [POST]  (/merge)
# /review/<id>/target       [POST]  (/review/<id>?action=target)
# /changeset/<id>
# /changeset/<id>/inspect   [POST]
# /changeset/<id>/build     [POST]
# /changeset/<id>/abandon   [POST]  (/review/<id>?action=abandon_changeset)
# /revision/<node>/abandon  [POST]  (/changes/new?action=abandon)


@app.route('/')
def index():
    return redirect(url_for('changes_active'))


@app.route('/changes/refresh', methods=["POST"])
@repo_write
@rework_db_write
@performance_monitor("Request /changes/refresh")
def changes_refresh():
    logger.info("Requested URL /changes/refresh")
    refresh_heads()
    if is_safe_url(request.referrer):
        return redirect(request.referrer)
    return redirect(url_for('changes_active'))


@app.route("/revision/<node>/abandon", methods=["POST"])
@login_required
@repo_write
@rework_db_write
@performance_monitor("Request /revision/<node>/abandon [POST]")
def revision_abandon(node):
    logger.info("Requested URL /revision/%s/abandon [POST]", node)
    refresh_heads()
    revision = repo.revision(node)
    rev_status = get_revision_status(repo, revision)
    if rev_status != "new" and rev_status != "rework":
        flash("Revision {0} is {1} and cannot be abandoned. Refresh list of revisions.".format(revision.node, rev_status), "error")
        logger.info("Revision {0} is {1} and cannot be abandoned".format(revision.node, rev_status))
        return redirect(url_for('changes_new'))
    #TODO: Multiple bookmarks
    changeset = Changeset(revision.name, revision.email, revision.title,
                          revision.node, el(revision.bookmarks),
                          "ABANDONED")
    db.session.add(changeset)
    Head.query.filter(Head.node == revision.node).delete()
    db.session.commit()
    repo.hg_close_branch(revision.node)
    if is_safe_url(request.referrer):
        return redirect(request.referrer)
    return redirect(url_for("changes_active"))


@app.route('/changes/new', defaults={'page': 1})
@app.route('/changes/new/<int:page>')
@rework_db_read
@performance_monitor("Request /changes/new")
def changes_new(page):
    logger.info("Requested URL /changes/new")

    query = Head.query.filter(Head.review_id == None)
    query = query.order_by(Head.created_date).paginate(page, app.config["PER_PAGE"])
    total = query.total
    revisions = query.items
    pagination = Pagination(page, app.config["PER_PAGE"], total)

    return render_template('new.html', revisions=revisions,
                           pagination=pagination)


@app.route('/changes/active', defaults={'page': 1})
@app.route('/changes/active/<int:page>')
def changes_active(page):
    form = SearchForm()
    data = get_reviews("ACTIVE", page, request)
    return render_template('active.html', reviews=data["r"],
                           form=form, pagination=data["p"])


@app.route('/changes/merged', defaults={'page': 1})
@app.route('/changes/merged/<int:page>')
def changes_merged(page):
    form = SearchForm()
    data = get_reviews("MERGED", page, request)
    return render_template('merged.html', reviews=data["r"], form=form, pagination=data["p"])


@app.route('/changeset/<int:cs_id>/inspect', methods=['POST'])
@login_required
@repo_read
@roles_required('user')
def inspect_diff(cs_id):
    cs = Changeset.query.filter(Changeset.id == cs_id).first()
    if cs is None:
        flash("Changeset {0} doesn't exist".format(cs_id), "error")
        logger.error("Changeset %d doesn't exist", cs_id)
        return redirect(url_for('index'))
    redirect_url = redirect(url_for('changeset_info', sha1=cs.sha1))
    if current_user.cc_login is None:
        flash("Code Collaborator login is not configured properly.", "error")
        logger.error("User account %s cc_login is not configured", current_user.email)
        return redirect_url
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
@repo_read
@roles_required('user')
def jenkins_build():
    info = repo.revision(request.form["src"])
    job_name = request.form["release"] + "-ci"
    changeset = Changeset.query.filter(Changeset.sha1 == info.node).first()
    build_info = jenkins.run_job(job_name, changeset.sha1)
    if build_info is None:
        flash("Scheduling Jenkins build failed", "error")
        return redirect(url_for("changeset_info", sha1=request.form["back_id"]))

    build = Build(changeset_id=changeset.id, status=build_info["status"],
                  job_name=job_name, build_url=build_info["build_url"])
    build.request_id = build_info["request_id"]
    build.scheduled = build_info["scheduled"]
    if "build_number" in build_info:
        build.build_number = build_info["build_number"]
    db.session.add(build)
    db.session.commit()
    logger.info("Jenkins build for changeset id " + str(changeset.id) +
                " has been added to queue. Changeset: " + str(changeset) +
                " , build: " + str(build))
    flash("Jenkins build has been added to the queue", "notice")
    return redirect(url_for('changeset_info', sha1=request.form['back_id']))


@app.route("/changeset/<int:changeset_id>/abandon", methods=["POST"])
@login_required
@repo_write
@performance_monitor("Request /changeset/<changeset_id>/abandon [POST]")
#TODO: If inspection scheduled, cannot abandon changeset
#TODO: Only active changeset or its descendant can be abandoned
#TODO: Abandoning active changeset should move bookmark backwards
def changeset_abandon(changeset_id):
    logger.info("Requested URL /changeset/%d/abandon [POST]", changeset_id)
    changeset = Changeset.query.filter(Changeset.id == changeset_id)
    if changeset is None:
        flash("Changeset {0} doesn't exist".format(changeset_id), "error")
        logger.error("Changeset %d doesn't exist", changeset_id)
        return redirect(url_for('index'))
    if not changeset.is_active():
        flash("Not active changeset cannot be abandoned", "error")
        logger.error("Changeset %d is not active and cannot be abandoned", changeset_id)
        return redirect(url_for('changeset_info', sha1=changeset.sha1))
    changeset.status = "ABANDONED"
    db.session.commit()
    repo.hg_sync()
    if changeset.sha1 in repo.hg_heads():
        repo.hg_close_branch(changeset.sha1)
    flash("Changeset '{title}' (SHA1: {sha1}) has been abandoned".format(title=changeset.title,
                                                                         sha1=changeset.sha1), "notice")
    return redirect(url_for("review_info", review_id=changeset.review_id))


@app.route('/changeset/<sha1>')
@performance_monitor("Request /changeset/<sha1>")
def changeset_info(sha1):
    logger.info("Requested URL /changeset/%s", sha1)
    cs = Changeset.query.filter(Changeset.sha1 == sha1).first()
    if cs is None:
        flash("Changeset {0} doesn't exist".format(sha1), "error")
        logger.error("Changeset %s doesn't exist", sha1)
        return redirect(url_for("index"))
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
    return render_template("changeset.html", review=review, cs=cs, next=next_,
                           prev=prev)


@app.route("/review", methods=["POST"])
@login_required
@repo_write
@rework_db_write
@performance_monitor("Request /review [POST]")
def review_new():
    logger.info("Requested URL /review [POST]")
    refresh_heads()
    revision = repo.revision(request.form['node'])
    rev_status = get_revision_status(repo, revision)
    if rev_status != "new":
        flash("Revision {0} is {1} and cannot be inspected. Refresh list of revisions.".format(revision.node, rev_status), "error")
        logger.info("Revision {0} is {1} and cannot be inspected.".format(revision.node, rev_status))
        return redirect(url_for('changes_new'))
    #TODO: Multiple bookmarks
    review = Review(owner=revision.name, owner_email=revision.email, title=revision.title,
                    bookmark=el(revision.bookmarks), status="ACTIVE")
    targets = repo.hg_targets(revision.rev, app.config['PRODUCT_BRANCHES'])
    review.add_targets(targets)
    #TODO: Multiple bookmarks
    changeset = Changeset(revision.name, revision.email, revision.title,
                          revision.node, el(revision.bookmarks),
                          "ACTIVE")
    review.changesets.append(changeset)
    db.session.add(review)
    Head.query.filter(Head.node == revision.node).delete()
    db.session.commit()
    return redirect(url_for('changeset_info', sha1=revision.node))


@app.route('/review/<int:review_id>', methods=["POST"])
@repo_write
@rework_db_write
@performance_monitor("Request /review/<int:review_id> [POST]")
def review_rework(review_id):
    logger.info("Requested URL /review/%d [POST]", review_id)
    review = Review.query.filter(Review.id == review_id).first()
    if review is None:
        flash("Review {0} doesn't exist".format(review_id), "error")
        logger.error("Review %d doesn't exist", review_id)
        return redirect(url_for("index"))
    refresh_heads()
    revision = repo.revision(request.form["node"])
    rev_status = get_revision_status(repo, revision)
    if rev_status != "rework":
        flash("Revision {0} is {1} and cannot be inspected. Refresh list of revisions.".format(revision.node, rev_status), "error")
        logger.info("Revision {0} is {1} and cannot be inspected.".format(revision.node, rev_status))
        return redirect(url_for('review_info', review_id=review.id))
    #TODO: Multiple bookmarks
    changeset = Changeset(revision.name, revision.email, revision.title,
                          revision.node, el(revision.bookmarks), "ACTIVE")
    changeset.review_id = review.id
    db.session.add(changeset)
    Head.query.filter(Head.node == revision.node).delete()
    Head.query.filter(Head.review_id == review.id).update({'review_id': None})
    db.session.commit()
    flash("Changeset '{title}' (SHA1: {sha1}) has been marked as rework".format(title=changeset.title, sha1=changeset.sha1),
          "notice")
    return redirect(url_for('changeset_info', sha1=revision.node))


@app.route('/review/<int:review_id>/abandon', methods=["POST"])
@repo_write
@performance_monitor("Request /review/<int:review_id>/abandon [POST]")
def review_abandon(review_id):
    logger.info("Requested URL /review/%d/abandon [POST]", review_id)
    review = Review.query.filter(Review.id == review_id).first()
    if review is None:
        flash("Review {0} doesn't exist".format(review_id), "error")
        logger.error("Review %d doesn't exist", review_id)
        return redirect(url_for("index"))
    review.status = "ABANDONED"
    Head.query.filter(Head.review_id == review.id).update({'review_id': None})
    db.session.commit()
    repo.hg_sync()
    heads = repo.hg_heads()
    for c in review.changesets:
        if c.sha1 in heads:
            repo.hg_close_branch(c.sha1)
    flash("Review has been abandoned", "notice")
    return redirect(url_for('changes_active'))


@app.route("/review/<int:review_id>/target", methods=["POST"])
def review_set_target(review_id):
    logger.info("Requested URL /review/%d/target [POST]", review_id)
    review = Review.query.filter(Review.id == review_id).first()
    if review is None:
        flash("Review {0} doesn't exist".format(review_id), "error")
        logger.error("Review %d doesn't exist", review_id)
        return redirect(url_for("index"))
    #TODO: If inspection scheduled, target cannot change
    try:
        review.set_target(request.form['target'])
    except Exception, ex:
        flash(str(ex), "error")
    else:
        db.session.commit()
        flash("Target branch has been set to <b>{0}</b>".format(review.target), "notice")
    return redirect(url_for('review_info', review_id=review.id))


@app.route('/review/<int:review_id>', methods=['GET'])
@performance_monitor("Request /review/<int:review_id>")
@rework_db_read
def review_info(review_id):
    logger.info("Requested URL /review/%d", review_id)
    review = Review.query.filter(Review.id == review_id).first()
    if review is None:
        flash("Review {0} doesn't exist".format(review_id), "error")
        logger.error("Review %d doesn't exist", review_id)
        return redirect(url_for("index"))
    reworks = Head.query.filter(Head.review_id == review.id)
    return render_template("review.html", review=review, descendants=reworks)


@app.route('/merge', methods=['POST'])
@login_required
@roles_required('admin')
@repo_write
@performance_monitor("Request /merge")
def merge_branch():
    sha1 = request.form['sha1']
    logger.info("Requested URL /merge for sha1=%s", sha1)
    changeset = Changeset.query.filter(Changeset.sha1 == sha1).first()
    review = Review.query.filter(Review.id == changeset.review_id).first()
    bookmark = review.target

    link = url_for("review_info", review_id=review.id, _external=True)

    refresh_heads()
    #TODO: Only active changeset can be merged

    logger.info("Merging %s into %s", sha1, review.target)
    repo.hg_update(bookmark)

    try:
        output = repo.hg_merge(sha1)
    except HgException as e:
        output = str(e)

    logger.info("Merge result: {output}".format(output=output))

    error = False
    subject = u"Successful merge '{name}' with {dest}".format(name=review.title, sha1=changeset.sha1, dest=review.target)

    if "abort: nothing to merge" in output:
        repo.hg_update(sha1)
        result = repo.hg_bookmark(bookmark, force=True)
        logger.info(result)
        flash("Changeset has been merged", "notice")
    elif "use 'hg resolve' to retry unresolved" in output:
        repo.hg_update("null", clean=True)
        flash("There is merge conflict. Merge with bookmark " + bookmark +
              " and try again.", "error")
        subject = u"Merge conflict - can't merge '{name}' with {dest}".format(name=review.title, sha1=changeset.sha1,
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

    html = subject + u"<br/><br/>Review link: <a href=\"{link}\">{link}</a><br/>Owner: {owner}<br/>SHA1: {sha1} ".format(
        link=link, sha1=changeset.sha1, owner=changeset.owner)

    recpts = [changeset.owner_email]
    recpts = list(set(recpts))

    msg = Message(subject,
                  sender=app.config["SECURITY_EMAIL_SENDER"],
                  recipients=recpts)
    msg.html = html
    mail.send(msg)

    if not error:
        review.status = "MERGED"
        review.close_date = datetime.datetime.utcnow()
        Head.query.filter(Head.review_id == review.id).update({'review_id': None})
        db.session.commit()
        flash("Review has been closed", "notice")

    return redirect(url_for('index'))


@app.route('/changelog/<start>/<stop>')
@login_required
@roles_required('admin')
@repo_read
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


@app.errorhandler(Exception)
def internal_error(ex):
    logger.exception(ex)
    import traceback
    error = {'message': str(ex), 'stacktrace': traceback.format_exc()}
    return render_template('500.html', error=error), 500

