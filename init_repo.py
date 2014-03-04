from app import app
from app.utils import repo_clone

with app.app_context():
    repo_clone(app.config["HG_PROD"])
