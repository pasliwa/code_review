import re
from hgapi.hgapi import Repo


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


