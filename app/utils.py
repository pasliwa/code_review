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
                b.status = 'Missing'
        db.session.add(b)
        db.session.commit()


def find_origin_inspection(changeset):
    review = Review.query.filter(Review.id == changeset.review_id).first()
    changesets = review.changesets
    ids = []
    map((lambda x: ids.append(x.id) if x.id else x), changesets)
    inspection = CodeInspection.query.filter(CodeInspection.changeset_id.in_(ids)).order_by(
        asc(CodeInspection.id)).first()
    return inspection


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


def get_new():
    heads = [repo.revision(node) for node in repo.hg_heads()]
    ignored_bookmarks = app.config["IGNORED_BRANCHES"] | \
                        app.config["PRODUCT_BRANCHES"]

    new = []
    for h in heads:
        if h.bookmarks & ignored_bookmarks:
            continue
        count = Changeset.query.filter(Changeset.sha1 == h.node).count()
        # make sure changeset is not part of any review
        if count < 1:
            # make sure changeset is not direct ancestor of changeset that is already in an active review
            #TODO: Multiple parents
            parent_rev = h.parents[0]
            parent = repo.revision(parent_rev)
            count = Changeset.query.filter(
                and_(Changeset.sha1 == parent.node, Changeset.review_id is not None)).count()
            if count < 1:
                new.append(h)

    reviews = []
    for h in new:
        #TODO: Multiple bookmarks
        #TODO: Do not return reviews here
        review = Review(owner=h.name, owner_email=h.email,
                        title=h.title, bookmark=el(h.bookmarks),
                        status="NEW")
        review.id = 0
        review.sha1 = h.node
        reviews.append(review)

    return reviews


def el(set_):
    l = list(set_)
    if len(l) == 0:
        return None
    else:
        return l[0]
