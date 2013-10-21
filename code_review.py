import os
from flask import Flask, redirect, url_for
from flask.globals import request
from flask.templating import render_template
from hgapi import HgException
from Jenkins import Jenkins
from Repo2 import Repo2
from database import db_session, init_db




# host: pl-byd-srv01.emea.int.genesyslab.com:18080/view/8.5/job/iwd_8.5.000-REVIEW/build/api/json
# x-www-form-urlencoded
# json       {"parameter":[{"name":"BRANCH","value":"MASTER"}]}
# encoded post : j  son=%7B%22parameter%22%3A%5B%7B%22name%22%3A%22BRANCH%22%2C%22value%22%3A%22MASTER%22%7D%5D%7D

#
#POST /view/8.5/job/iwd_8.5.000-REVIEW/build/api/json HTTP/1.1
#Host: pl-byd-srv01.emea.int.genesyslab.com:18080
#Cache-Control: no-cache
#Content-Type: application/x-www-form-urlencoded
#
#json=%7B%22parameter%22%3A%5B%7B%22name%22%3A%22BRANCH%22%2C%22value%22%3A%22MASTER%22%7D%5D%7D
from models import Review, Build


app = Flask(__name__)
app.config.from_object("config")

currDir = os.path.dirname(__file__)
repo = Repo2(os.path.join(currDir, "repo"))
productBranches = ["default", "master", "iwd-8.1.000", "iwd-8.1.001", "iwd-8.1.101", "iwd-8.0.001", "iwd-8.0.002", "iwd-8.0.003"]

jenkins = Jenkins("http://pl-byd-srv01.emea.int.genesyslab.com:18080")

#Build.query.filter(Build.review_id == 1).all()
res = Review.query.filter(Review.id == 1).first()
print dir(res.builds)
res.builds.append(Build(None, "111", "sssss"))
db_session.add(res)
db_session.commit()
init_db()

#u = User('admin', 'admin@localhost')
#db_session.add(u)
#db_session.commit()

@app.route('/')
def index():
    return redirect(url_for('changes_new'))


@app.route('/changes/new')
def changes_new():
    #branches = repo.get_branch_names()
    #heads = repo.hg_heads()
    #bookmarks=repo.hg_bookbarks()
    #branches.remove("default") if "default" in branches else ""
    #branches=branches+bookmarks
    heads = repo.hg_heads()
    for h in heads:
        if h['branches']:
            h['src'] = h['branches']
        else:
            h['src'] = h['bookmarks']
        sha1 = repo.hg_log(identifier=h['rev'], template="{node}")
        count = Review.query.filter(Review.sha1 == sha1).count()
        if (count < 1):
            review = Review("dummy user", "dummy@email.com", h["desc"], sha1)
            db_session.add(review)
            db_session.commit()
            b = Build(review.id, "aaa", "aaa")
            db_session.add(b)
            db_session.commit()

    return render_template('changes.html', type="New", heads=heads, productBranches=productBranches)


@app.route('/changes/latest')
def changes_latest():
    return changes_latest_in_branch("default")


@app.route('/changes/latest/<branch>')
def changes_latest_in_branch(branch):
    log = repo.hg_log(branch=branch, limit=30)
    return render_template('log.html', log=log, branch=branch)


@app.route('/merge/<branch>')
def merge_with_default(branch):
    return merge_branch(branch, "default")


@app.route('/merge', methods=['POST'])
def merge_from_post():
    return merge_branch(request.form['src'], request.form['dst'])


@app.route('/build', methods=['POST'])
def jenkins_build():
    res = jenkins.run_job("iwd_8.5.000-REVIEW", "default")
    return render_template('changes.html', type="Merging")


@app.route('/merge/<src>/<dst>')
def merge_branch(src, dst):
    msg = ""
    e = ""
    diff = ""
    try:
        diff = repo.hg_log(branch=src)
        repo.hg_update(src)
        branches = repo.get_branch_names()
        bookmarks = repo.hg_bookbarks(True)
        heads = repo.hg_heads()
        if src in branches:
            res2 = repo.hg_commit("Closing branch {src}".format(src=src), user="me", close_branch=True)
        res3 = repo.hg_update(dst)
        res4 = repo.hg_merge(src)
        for h in heads:
            if h["branches"] == src or h["bookmarks"] == src:
                title = h['desc']
        res5 = repo.hg_commit("Merge '{desc}' ({src}) with {dst}".format(src=src, dst=dst, desc=title), user="me", close_branch=False)
        if src in bookmarks:
            res6 = repo.hg_bookmark(src, delete=True)
        msg = "'{desc}' in branch '{src}' was successfully merged with '{dst}. <br/>Changes: <br><pre>{diff}</pre>'".format(src=src, dst=dst, diff=diff, desc=title)
    except HgException, e:
        print "===" + str(e)
    return render_template('changes.html', type="Merging", branch=src, exception=e, message=msg, diff=diff)
    #return render_template('changes.html', type="Merging", src=src, dst=dst)


@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

if __name__ == '__main__':
    app.run(host='0.0.0.0')
