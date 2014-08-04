import os.path
import shutil
import logging

from app import app
from app import logs
from app.mercurial import Repo

logging.getLogger().setLevel(logging.INFO)
logging.getLogger().setHandler(logs.get_console_handler())

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
