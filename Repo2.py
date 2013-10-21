import re
from hgapi.hgapi import Repo

# http://hgbook.red-bean.com/read/customizing-the-output-of-mercurial.html

class Repo2(Repo):
    def hg_bookbarks(self, namesOnly=True):
        output=self.hg_command("bookmarks")
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
        """
            Get a list with the node identifiers of all open heads.
            If short is given and is not False, return the short
            form of the node id.
        """
        res = []
        template = "{rev}:::{desc|firstline}:::{bookmarks}:::{branches}\n"
        output = self.hg_command("heads", "--template", template)
        reg_expr = "(?P<rev>\d+):::(?P<desc>[\s\w\S]+):::(?P<bookmarks>[\s\w\S]{0,}):::(?P<branches>[\s\w\S]{0,})"
        pattern = re.compile(reg_expr)
        for row in output.strip().split('\n'):
            match = pattern.search(row)
            if match is not None:
                bm = match.group("bookmarks")
                if bm == "":
                    bm = None;
                br = match.group("branches")
                if br == "":
                    br = None
                res.append({"rev": match.group("rev"), "desc": match.group("desc"), "bookmarks" : bm , "branches": br})
        return res


