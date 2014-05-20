import os.path

dname = os.path.dirname(__file__)
root_dir = os.path.abspath(os.path.join(dname, '..'))

import config
config.SQLALCHEMY_DATABASE_URI = "sqlite://"
config.REPO_PATH = os.path.join(root_dir, "tmp/repo_clone")
config.TESTING = True
config.DEBUG = True
config.WTF_CSRF_ENABLED = False

REPO_MASTER = os.path.join(root_dir, "tmp/repo_master")
