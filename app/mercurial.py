import os
import re
import logging
import dateutil.parser

from hgapi import hgapi
from app.perfutils import PerformanceMonitor

# http://hgbook.red-bean.com/read/customizing-the-output-of-mercurial.html

logger = logging.getLogger(__name__)


class MergeConflictException(hgapi.HgException):
    def __init__(self, hg_exception):
        super(MergeConflictException, self).__init__(hg_exception.message)
        self.exit_code = hg_exception.exit_code


class Revision(hgapi.Revision):
    def __init__(self, json_log):
        try:
            super(Revision, self).__init__(json_log)
            self.bookmarks = set(self.bookmarks.split())
            self.date = dateutil.parser.parse(self.date)
        except:
            logger.error("Error in Revision.init(). Json log:\n%s", json_log)
            raise

hgapi.Revision = Revision


class Repo(hgapi.Repo):

    @classmethod
    def command(cls, path, env, *args):
        """
            Run a hg command in path and return the result.

            Raise on error.
        """
        #with open(os.devnull, 'r') as DEVNULL:
        proc = Popen(["hg", "--cwd", path, "--encoding", "UTF-8"] + list(args),
                         stdout=PIPE, stderr=PIPE, env=env)
                         
        out, err = [x.decode("utf-8") for x in proc.communicate()]

        if proc.returncode:
            cmd = (" ".join(["hg", "--cwd", path] + list(args)))
            raise HgException("Error running %s:\n\" + "
                                "tErr: %s\n\t"
                                "Out: %s\n\t"
                                "Exit: %s"
                                % (cmd, err, out, proc.returncode),
                                exit_code=proc.returncode)

        return out
    
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

    def revisions(self, slice_):
        a, b = slice_
        id_ = str(a) + "::" + str(b)
        out = self.hg_log(identifier=id_, template=self.rev_log_tpl)

        revs = []
        for entry in out.split('\n')[:-1]:
            revs.append(Revision(entry))

        return revs

    def hg_merge(self, reference, preview=False):
        if preview:
            return hgapi.Repo.hg_merge(reference, True)
        try:
            return self.hg_command("--config", "ui.interactive=1", "merge", "--tool", "internal:merge", reference)
        except hgapi.HgException, ex:
            if "use 'hg resolve' to retry" in ex.message:
                raise MergeConflictException(ex)
            raise

    def hg_push(self, destination=None):
        if destination is None:
            self.hg_command("push", "-f")
        else:
            self.hg_command("push", "-f", destination)

    def hg_purge(self):
        self.hg_command("purge")

    def hg_incoming_bookmarks(self, source=None):
        try:
            if source is None:
                output = self.hg_command("incoming", "-B")
            else:
                output = self.hg_command("incoming", "-B", source)
        except hgapi.HgException, ex:
            if "no changed bookmarks found" in ex.message:
                return []
            raise
        result = []
        for line in output.split('\n')[2:-1]:
            bookmark, node = line.split()
            result.append(bookmark)
        return result

    def hg_pull_bookmark(self, bookmark, source=None):
        logger.debug("Pulling bookmark %s", bookmark)
        if source is None:
            self.hg_command("pull", "-B", bookmark)
        else:
            self.hg_command("pull", "-B", bookmark, source)

    def hg_pull(self, source=None):
        hgapi.Repo.hg_pull(self, source)
        for bookmark in self.hg_incoming_bookmarks(source):
            self.hg_pull_bookmark(bookmark, source)

    def hg_ancestor(self, identifier1, identifier2):
        query = "ancestor('{0}','{1}')".format(identifier1, identifier2)
        res = self.hg_command("log", "-r", query, "--template", "{node}")
        logger.debug("Ancestor for %s and %s is revision %s",
                     identifier1, identifier2, res.strip())
        return res.strip()

    def hg_compare(self, identifier1, identifier2):
        node1 = self.revision(identifier1).node
        node2 = self.revision(identifier2).node
        if node1 == node2:
            return 0
        ancestor = self.hg_ancestor(node1, node2)
        if ancestor == node1:
            return -1
        elif ancestor == node2:
            return 1
        else:
            raise Exception("Revisions %s and %s are not comparable",
                            identifier1, identifier2)

    def hg_targets(self, identifier, product_bookmarks):
        ancestors = {}
        for bookmark in sorted(product_bookmarks, reverse=True):
            ancestor = self.hg_ancestor(identifier, bookmark)
            if not ancestor in ancestors:
                ancestors[ancestor] = []
            ancestors[ancestor].append(bookmark)
        if not ancestors:
            return []
        ancestor_ids = ancestors.keys()
        youngest = ancestor_ids[0]
        for candidate in ancestor_ids[1:]:
            if self.hg_compare(youngest, candidate) < 0:
                youngest = candidate
        return ancestors[youngest]

    diverged_regexp = re.compile("(?P<bookmark>[\s\w\S]+)@default")

    official_re = re.compile('^iwd-\d.\d.\d{3}$')

    #TODO: Check if repo is always reset to bare.
    #TODO: Race conditions on repository access
    def hg_sync(self):
        logger.info("Performing hg_sync")
        with PerformanceMonitor("hg_sync: hg_pull"):
            old_bookmarks = self.hg_bookmarks()
            self.hg_pull()
            new_bookmarks = self.hg_bookmarks()

        for b in set(old_bookmarks.keys() + new_bookmarks.keys()):
            if not self.official_re.match(b):
                continue
            elif not b in new_bookmarks:
                logger.warn("Official bookmark %s mysteriously disappeared "
                            "in hg_sync", b)
            elif not b in old_bookmarks:
                logger.warn("Official bookmark %s appeared in hg_sync", b)
            elif new_bookmarks[b] != old_bookmarks[b]:
                logger.warn("Official bookmark %s changed position "
                            "from %s to %s in hg_sync", b,
                            old_bookmarks[b], new_bookmarks[b])

        for b in new_bookmarks.keys():
            match = self.diverged_regexp.search(b)
            if match is not None:
                with PerformanceMonitor("hg_sync: hg_merge"):
                    logger.warn("Detected diverged bookmark %s with node %s. "
                                "Attempting merge.", b, new_bookmarks[b])
                    core_bookmark = match.group("bookmark")
                    self.hg_update(core_bookmark)
                    try:
                        self.hg_merge(b)
                        self.hg_commit("Merge of divergent branch {0}".format(b))
                        logger.warn("Merge of diverged bookmark %s successful.", b)
                    except:
                        logger.error("Unsuccessful merge of diverged bookmark %s",
                                     b, exc_info=True)
                        raise
                    finally:
                        self.hg_update("null", clean=True)
                    self.hg_bookmark(b, delete=True)
                    self.hg_push()

        with PerformanceMonitor("hg_sync: hg_push"):
            try:
                self.hg_push()
                logger.warn("Detected unsuccessful push. Fixed during hg_sync.")
            except hgapi.HgException, ex:
                if not "no changes found" in ex.message:
                    raise

    def hg_close_branch(self, identifier):
        self.hg_update(identifier, clean=True)
        self.hg_commit("Abandon changeset", close_branch=True)
        self.hg_update("null", clean=True)
        self.hg_push()

    @classmethod
    def hg_clone(cls, url, path, *args):
        Repo.command(".", os.environ, "clone", url, path, *args)
        return Repo(path)
