import os
import shutil
from sqlalchemy import asc
from app import jenkins, db, User, Role, app, repo
from app.models.Build import Build
from app.models.CodeInspection import CodeInspection
from app.models.Review import Review


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



def get_admin_emails():
    admins =  []
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
    repo.hg_clone(url, path)
    repo.hg_update("null", True)