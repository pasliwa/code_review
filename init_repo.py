import os.path
import shutil

from app import app
from app.mercurial import Repo

with app.app_context():
    url = app.config["HG_PROD"]
    path = app.config["REPO_PATH"]
    if os.path.exists(path):
        shutil.rmtree(path)
    os.mkdir(path)
    print("HG clone repo '{repo}' into '{path}'".format(repo=url, path=path))
    repo = Repo.hg_clone(url, path)
    repo.hg_update("null", True)
    print("HG clone finished")
