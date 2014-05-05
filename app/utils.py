import os
import shutil
from sqlalchemy import asc
from sqlalchemy.sql import desc, and_
from app import jenkins, db, User, Role, app, repo
from app.model import Build, Changeset
from app.model import CodeInspection
from app.model import Review
from app.view import Pagination


def update_build_status(changeset):
    builds = Build.query.filter(Build.changeset_id == changeset).all()
    for b in builds:
        if b.build_number is not None:
            build_info = jenkins.get_build_info(b.job_name, b.build_number)
            b.status = build_info['status']
        elif jenkins.check_queue(b.job_name, b.request_id):
            b.status = 'Queued'
        else:
            build_info = jenkins.find_build(b.job_name, b.request_id)
            if build_info is not None:
                b.status = build_info['status']
                b.build_number = build_info['build_number']
                b.build_url = build_info['build_url']
            else:
                if b.status != "SCHEDULED":
                    b.status = 'Missing'
        db.session.add(b)
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


def repo_clone(url):
    path = app.config["REPO_PATH"]
    if os.path.exists(path):
        shutil.rmtree(path)
    os.mkdir(path)
    print("HG clone repo '{repo}' into '{path}'".format(repo=url, path=path))
    repo.hg_clone(url, path)
    repo.hg_update("null", True)
    print("HG clone finished")


def get_reviews(status, page, request):
    f = Review.query.filter(Review.status == status)
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


def is_descendant(node, parents):
    for chset in parents:
        if repo.hg_ancestor(node, chset) == chset:
            return True
    return False


def get_new():
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
        if is_descendant(h.node, active):
            continue
        result.append(h)

    return result


def get_reworks(review):
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
        if not is_descendant(head.node, [active.sha1]):
            continue
        result.append(head)
    return result


def el(set_):
    l = list(set_)
    if len(l) == 0:
        return None
    else:
        return l[0]
