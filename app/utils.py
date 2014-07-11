import logging
from sqlalchemy.sql import desc
from app import jenkins, db, User, Role, app
from app.model import Build, Changeset
from app.model import Review
from app.view import Pagination
from app.perfutils import performance_monitor

logger = logging.getLogger(__name__)

def known_build_numbers(job_name):
    query = db.session.query(Build.build_number)\
        .filter(Build.job_name == job_name)\
        .filter(Build.build_number != None)
    return [int(row.build_number) for row in query.all()]

jenkins_final_states = ["FAILURE", "UNSTABLE", "SUCCESS", "ABORTED"]

@performance_monitor("update_build_status")
def update_build_status(changeset):
    logger.info("Updating build status for changeset %s", changeset)
    builds = Build.query.filter(Build.changeset_id == changeset).all()
    for b in builds:
        if b.status == "SCHEDULED":
            logger.debug("Build scheduled. Skipping")
            continue
        elif b.status in jenkins_final_states:
            logger.debug("Build %d in final state %s. Skipped", b.build_number,
                         b.status)
            continue
        elif b.build_number is not None:
            b.status = jenkins.get_build_status(b.job_name, b.build_number)
        elif jenkins.check_queue(b.job_name, b.request_id):
            b.status = 'Queued'
        else:
            builds = set(jenkins.list_builds(b.job_name)) - set(known_build_numbers(b.job_name))
            for build_number in builds:
                build_info = jenkins.get_build_info(b.job_name, build_number)
                if build_info["request_id"] == b.request_id:
                    b.status = build_info['status']
                    b.build_number = build_number
                    b.build_url = build_info["build_url"]
                    logger.debug("Build found with number %d and status %s",
                                 b.build_number, b.status)
                    break
            else:
                b.status = "Missing"
        db.session.commit()


def get_admin_emails():
    admins = []
    try:
        adms = User.query.join(User.roles).filter(Role.name == "admin").all()
        for a in adms:
            admins.append(a.email)
    except Exception:
        pass
    return admins


def get_reviews(status, page, request):
    f = Review.query.filter(Review.status == status)
    author = request.args.get('author', None)
    title = request.args.get('title', None)
    if author:
        f = f.filter((Review.owner.contains(author)))
    if title:
        f = f.filter((Review.title.contains(title)))
    if status == "MERGED":
        query = f.order_by(desc(Review.close_date)).paginate(page, app.config["PER_PAGE"], False)
    else:
        query = f.order_by(desc(Review.created_date)).paginate(page, app.config["PER_PAGE"], False)
    total = query.total
    reviews = query.items
    pagination = Pagination(page, app.config["PER_PAGE"], total)
    return {"r": reviews, "p": pagination}


def get_active_changesets():
    reviews = Review.query.filter(Review.status == "ACTIVE")
    changesets = []
    for review in reviews:
        for changeset in review.changesets:
            if changeset.status == "ACTIVE":
                changesets.append(changeset)
                break
    return changesets


def is_descendant(repo, node, parents):
    for chset in parents:
        if repo.hg_ancestor(node, chset) == chset:
            return True
    return False


def get_new(repo):
    heads = [repo.revision(node) for node in repo.hg_heads()]
    active = [changeset.sha1 for changeset in get_active_changesets()]
    abandoned = set([changeset.sha1 for changeset in
                    Changeset.query.filter(Changeset.status == "ABANDONED")])
    ignored_bookmarks = app.config["IGNORED_BRANCHES"] | \
                        app.config["PRODUCT_BRANCHES"]

    result = []
    for h in heads:
        if h.bookmarks & ignored_bookmarks:
            continue
        if h.node in abandoned:
            continue
        if is_descendant(repo, h.node, active):
            continue
        result.append(h)

    return result


def get_reworks(repo, review):
    if review.status != "ACTIVE":
        return []
    active = review.active_changeset()
    if active is None:
        return []

    heads = [repo.revision(node) for node in repo.hg_heads()]
    changesets = set([changeset.sha1 for changeset in Changeset.query.all()])
    ignored_bookmarks = app.config["IGNORED_BRANCHES"] | \
                        app.config["PRODUCT_BRANCHES"]

    result = []
    for head in heads:
        if head.bookmarks & ignored_bookmarks:
            continue
        if head.node in changesets:
            continue
        if not is_descendant(repo, head.node, [active.sha1]):
            continue
        result.append(head)
    return result


def el(set_):
    l = list(set_)
    if len(l) == 0:
        return None
    else:
        return l[0]


