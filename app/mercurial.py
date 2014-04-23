import re
import logging

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

    def hg_ancestor(self, identifier1, identifier2):
        query = "ancestor({0},{1})".format(identifier1, identifier2)
        res = self.hg_command("log", "-r", query, "--template", "{node}")
        return res.strip()

    def hg_target(self, identifier, official_bookmarks):
        ancestors = {}
        for bookmark in official_bookmarks:
            ancestor = self.hg_ancestor(identifier, bookmark)
            if not ancestor in ancestors:
                ancestors[ancestor] = []
            ancestors[ancestor].append(bookmark)
        if not ancestors:
            return []
        ancestor_ids = ancestors.keys()
        target_ancestor_id = ancestor_ids[0]
        for ancestor_id in ancestor_ids[1:]:
            target_ancestor_id = self.hg_ancestor(target_ancestor_id,
                                                  ancestor_id)
        if not target_ancestor_id in ancestors:
            logging.error("Target ancestor id %s not within list of ancestors"
                          " for changeset %s", target_ancestor_id, identifier)
            return []
        return ancestors[target_ancestor_id]

