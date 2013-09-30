import os
from flask import Flask, redirect, url_for
from flask.templating import render_template
from hgapi import HgException
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
    branches.remove("default") if "default" in branches else ""
    return render_template('changes.html', type="New", branches=branches)


@app.route('/merge/<branch>')
def merge_with_default(branch):
    return merge_branch(branch, "default")


@app.route('/merge/<src>/<dst>')
def merge_branch(src, dst):
    msg = ""
    e = ""
    diff = ""
    try:
        diff = repo.hg_log(branch=src)
        repo.hg_update(src)
        res2=repo.hg_commit("Closing branch {src}".format(src=src), user="me", close_branch=True)
        res3=repo.hg_update(dst)
        res4=repo.hg_merge(src)
        res5=repo.hg_commit("Merge {src} with {dst}".format(src=src, dst=dst), user="me", close_branch=False)
        msg = "Branch '{src}' was successfully merged with '{dst}. <br/>Changes: <br><pre>{diff}</pre>'".format(src=src, dst=dst, diff=diff)
    except HgException,e:
        print "===" + str(e)
    return render_template('changes.html', type="Merging", branch=src, exception=e, message=msg, diff=diff)
    #return render_template('changes.html', type="Merging", src=src, dst=dst)


@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

if __name__ == '__main__':
    app.run(host='0.0.0.0')
