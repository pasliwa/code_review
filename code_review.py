import os
from flask import Flask, redirect, url_for
from flask.templating import render_template
from database import db_session
import hgapi
import shutil

app = Flask(__name__)
app.config.from_object("config")

currDir = os.path.dirname(__file__)
repo = hgapi.Repo(os.path.join(currDir, "repo"))
productBranches = ["iwd-8.1.000", "iwd-8.1.001", "iwd-8.1.101", "iwd-8.0.001", "iwd-8.0.002", "iwd-8.0.003", "default"]


@app.route('/')
def index():
    return redirect(url_for('changes_new'))


@app.route('/changes/new')
def changes_new():
    branches = repo.get_branch_names()
    branches.remove("default")
    return render_template('changes.html', type="New", branches=branches)


@app.route('/merge/<branch>')
def merge_branch(branch):
    return render_template('changes.html', type="Merging", branch=branch)



@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

if __name__ == '__main__':
    app.run(host='0.0.0.0')
