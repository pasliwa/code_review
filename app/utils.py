import os
import shutil
from sqlalchemy import asc
from sqlalchemy.sql import desc, and_
from app import jenkins, db, User, Role, app, repo
from app.model import Build, Changeset
from app.model import CodeInspection
from app.model import Review
from app.view import SearchForm, Pagination


def update_build_status(changeset):
    builds = Build.query.filter(Build.changeset_id == changeset).all()
    for b in builds:
        build_info = jenkins.get_build_info(b.job_name, b.build_number)
        if build_info == None:
            continue
        b.status = build_info["result"]
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
    temp = repo.hg_heads()
    heads, new, reviews = [], [], []

    # remove all official bookmarks
    map((lambda x: heads.append(x) if x["bookmarks"] not in app.config["IGNORED_BRANCHES"] + app.config[
        "PRODUCT_BRANCHES"] else x), temp)

    for h in heads:
        h['src'] = h['bookmarks']
        sha1 = repo.hg_log(identifier=h['rev'], template="{node}")
        count = Changeset.query.filter(Changeset.sha1 == h["changeset"]).count()
        # make sure changeset is not part of any review
        if (count < 1):
            # make sure changeset is not direct ancestor of changeset that is already in an active review
            parent_rev = repo.hg_parent(sha1)
            parent = repo.hg_rev_info(parent_rev)
            count = Changeset.query.filter(
                and_(Changeset.sha1 == parent["changeset"], Changeset.review_id != None)).count()
            if (count < 1):
                new.append(h)

    for h in new:
        review = Review(owner=h["author"], owner_email=h["email"], title=h["desc"],
                        bookmark=h["bookmarks"], status="NEW", target="iwd-8.5.000")
        review.id = 0
        review.sha1 = h["changeset"]
        reviews.append(review)

    return reviews

