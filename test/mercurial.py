import os
import shutil

from app.mercurial import Repo

from sandbox import config, REPO_MASTER

def modfile(file_name, line_no, line_text):
    lines = []
    if os.path.exists(file_name):
        lines = file(file_name, "r").readlines()
    lines.extend([""] * (line_no + 1 - len(lines)))
    lines[line_no] = line_text
    file(file_name, "w").writelines(lines)

FILE_1 = os.path.join(REPO_MASTER, "file1.txt")
FILE_2 = os.path.join(config.REPO_PATH, "file1.txt")


class MercurialBase:

    def commit_master(self, line_text, file_name=FILE_1, rev=None, line_no=0,
                      bmk=None, tag=None):
        if rev:
            self.master.hg_update(rev, clean=True)
        if bmk:
            self.master.hg_bookmark(bmk, force=True)
        modfile(file_name, line_no, line_text)
        self.master.hg_add(file_name)
        self.master.hg_commit(line_text)
        if tag:
            self.master.hg_tag(tag, "--local")
        return self.master.hg_id()

    def commit_slave(self, line_text, file_name=FILE_2, rev=None, line_no=0,
                     bmk=None, tag=None):
        if rev:
            self.slave.hg_update(rev, clean=True)
        if bmk:
            self.slave.hg_bookmark(bmk, force=True)
        modfile(file_name, line_no, line_text)
        self.slave.hg_add(file_name)
        self.slave.hg_commit(line_text)
        if tag:
            self.slave.hg_tag(tag, "--local")
        return self.slave.hg_id()

    def init_repos(self):
        if os.path.exists(REPO_MASTER):
            shutil.rmtree(REPO_MASTER)
        if os.path.exists(config.REPO_PATH):
            shutil.rmtree(config.REPO_PATH)
        os.makedirs(REPO_MASTER)
        self.master = Repo(REPO_MASTER)
        self.master.hg_init()
        #TODO: Bug in mercurial.py. Should return mercurial.Repo, returns hgapi.Repo
        Repo.hg_clone(REPO_MASTER, config.REPO_PATH)
        self.slave = Repo(config.REPO_PATH)