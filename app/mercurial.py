import re
from hgapi import hgapi

# http://hgbook.red-bean.com/read/customizing-the-output-of-mercurial.html

class Revision(hgapi.Revision):
    def __init__(self, json_log):
        super(Revision, self).__init__(json_log)
        self.bookmarks = set(self.bookmarks.split())

hgapi.Revision = Revision

class Repo(hgapi.Repo):
    def hg_bookmarks(self):
        output = self.hg_command("bookmarks")
        res = {}
        reg_expr = "(?P<bookmark>\S+)\s+(?P<rev>\d+):(?P<changeset>\w+)"
        pattern = re.compile(reg_expr)
        for row in output.strip().split('\n'):
            match = pattern.search(row)
            if match is not None:
                bookmark = match.group("bookmark")
                changeset = match.group("changeset")
                res[bookmark] = changeset
        return res

    def hg_bookmark(self, bookmark, delete=False, force=False):
        cmd = ["bookmark", str(bookmark)]
        if delete:
            cmd.append("--delete")
        if force:
            cmd.append("--force")
        return self.hg_command(*cmd)

    rev_log_tpl = (
        '\{"node":"{node}","rev":"{rev}","author":"{author|urlescape}",'
        '"name":"{author|person|urlescape}","email":"{author|email|urlescape}",'
        '"branch":"{branches}","parents":"{parents}","date":"{date|isodate}",'
        '"bookmarks":"{bookmarks}","title":"{desc|firstline|urlescape}",'
        '"tags":"{tags}","desc":"{desc|urlescape}\"}\n'
    )

    def hg_merge(self, reference):
        return self.hg_command("merge", "--tool", "internal:fail", reference)

