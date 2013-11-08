import re
from hgapi.hgapi import Repo

# http://hgbook.red-bean.com/read/customizing-the-output-of-mercurial.html

class Repo2(Repo):
    def hg_bookbarks(self, namesOnly=True):
        output = self.hg_command("bookmarks")
        res = {}
        reg_expr = "(?P<bookmark>\S+)\s+(?P<rev>\d+):(?P<changeset>\w+)"
        pattern = re.compile(reg_expr)
        for row in output.strip().split('\n'):
            match = pattern.search(row)
            if match is not None:
                bookmark = match.group("bookmark")
                changeset = match.group("changeset")
                res[bookmark] = {"changeset": changeset, "rev": match.group("rev")}
        return res.keys() if namesOnly else res

    def hg_bookmark(self, bookmark, delete=False):
        cmd = ["bookmark", str(bookmark)]
        if delete:
            cmd.append("--delete")
        return self.hg_command(*cmd)

    def hg_heads(self):
        res = []
        template = "{rev}:::{desc|firstline}:::{bookmarks}:::{node}:::{author|person}:::{author|email}\n"
        output = self.hg_command("heads", "--template", template)
        reg_expr = "(?P<rev>\d+):::(?P<desc>[\s\w\S]+):::(?P<bookmarks>[\s\w\S]{0,}):::(?P<changeset>[\d\w]+):::(?P<user>[\s\w\S]+):::(?P<email>[\s\w\S]{0,})"
        pattern = re.compile(reg_expr)
        for row in output.strip().split('\n'):
            match = pattern.search(row)
            if match is not None:
                bm = match.group("bookmarks")
                if bm != "":
                    res.append({"rev": match.group("rev"), "desc": match.group("desc"), "bookmarks": bm,
                                "changeset": match.group("changeset"), "author": match.group("user"),
                                "email": match.group("email")})
        return res

    def hg_head_changeset_info(self, changeset):
        heads = self.hg_heads()
        for h in heads:
            if h["changeset"] == changeset:
                return h
        return None

    def hg_head_branch_info(self, branch):
        heads = self.hg_heads()
        for h in heads:
            if h["branches"] == branch:
                return h
        return None

    def hg_head_bookmark_info(self, bookmark):
        heads = self.hg_heads()
        for h in heads:
            if h["bookmarks"] == bookmark:
                return h
        return None

