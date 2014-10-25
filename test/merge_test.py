import os
import unittest

from app.hgapi.hgapi import HgException
from app.mercurial import MergeConflictException
from test.mercurial import config, MercurialBase

FILE_3 = os.path.join(config.REPO_PATH, "file2.txt")


class MergeTest(MercurialBase):

    def test_failed_push_recovery(self):
        self.init_repos()
        self.commit_master("Initial creation")
        rev1 = self.commit_master("Last commit in official repo",
                                  bmk="iwd-8.5.000")
        self.slave.hg_pull()
        rev2 = self.commit_slave("Non-pushed commit in local repo",
                                 rev="iwd-8.5.000")
        self.slave.hg_sync()
        self.assertTrue("iwd-8.5.000" in self.master.revision(rev2).bookmarks)
        self.assertTrue("iwd-8.5.000" in self.slave.revision(rev2).bookmarks)

    def test_advance_branch_recovery(self):
        self.init_repos()
        self.commit_master("Initial creation")
        rev1 = self.commit_master("Last commit in both repos",
                                  bmk="iwd-8.5.000")
        self.slave.hg_pull()
        rev2 = self.commit_master("Advance commit in official repo")
        self.slave.hg_sync()
        self.assertTrue("iwd-8.5.000" in self.master.revision(rev2).bookmarks)
        self.assertTrue("iwd-8.5.000" in self.slave.revision(rev2).bookmarks)

    def test_conflicting_changes_during_sync(self):
        self.init_repos()
        self.commit_master("Initial creation", bmk="iwd-8.5.000")
        self.slave.hg_pull()
        rev1 = self.commit_master("Conflicting change in master")
        rev2 = self.commit_slave("Conflicting change in slave",
                                 rev="iwd-8.5.000")
        try:
            self.slave.hg_sync()
            self.fail("conflicting changes during sync didn't raise exception")
        except MergeConflictException, ex:
            pass
        else:
            fail("Exception raised, but not MergeConflict.")
        self.assertTrue("iwd-8.5.000" in self.master.revision(rev1).bookmarks)
        self.assertRaises(HgException, self.master.revision, rev2)
        self.assertTrue("iwd-8.5.000" in self.slave.revision(rev2).bookmarks)
        self.assertTrue("iwd-8.5.000@default" in self.slave.revision(rev1).bookmarks)

    def test_diverged_branches_recovery(self):
        self.init_repos()
        self.commit_master("Initial creation", bmk="iwd-8.5.000")
        self.slave.hg_pull()
        rev1 = self.commit_master("Non-conflicting change in master")
        rev2 = self.commit_slave("Non-conflicting change in slave",
                                 rev="iwd-8.5.000", file_name=FILE_3)
        self.slave.hg_sync()
        self.assertEqual(self.master.revision(rev1).bookmarks, set([]))
        self.assertEqual(self.master.revision(rev2).bookmarks, set([]))
        self.assertEqual(self.slave.revision(rev1).bookmarks, set([]))
        self.assertEqual(self.slave.revision(rev2).bookmarks, set([]))
        rev3 = self.master.revision("iwd-8.5.000").node
        self.assertTrue("iwd-8.5.000" in self.slave.revision(rev3).bookmarks)
        self.assertFalse("iwd-8.5.000@default" in self.master.hg_bookmarks().keys())
        self.assertFalse("iwd-8.5.000@default" in self.slave.hg_bookmarks().keys())

    def test_multiple_failed_branches(self):
        self.init_repos()
        self.commit_master("Initial creation")
        self.commit_master("Non-conflicting merge root", bmk="iwd-8.0.003")
        self.commit_master("Rogue commit root", bmk="iwd-8.1.101")
        rev5 = self.commit_master("Failed push root", bmk="iwd-8.5.000")
        rev3 = self.commit_master("Official commit", rev="iwd-8.1.101")
        self.slave.hg_pull()
        rev1 = self.commit_master("Official non-conflicting commit",
                                  rev="iwd-8.0.003")
        rev2 = self.commit_slave("Rogue non-conflicting commit",
                                 rev="iwd-8.0.003", file_name=FILE_3)
        rev4 = self.commit_master("Rogue commit", rev="iwd-8.1.101")
        rev6 = self.commit_slave("Official non-pushed commit",
                                 rev="iwd-8.5.000")
        self.slave.hg_sync()
        self.assertEqual(self.master.revision(rev1).bookmarks, set([]))
        self.assertEqual(self.slave.revision(rev1).bookmarks, set([]))
        self.assertEqual(self.master.revision(rev2).bookmarks, set([]))
        self.assertEqual(self.slave.revision(rev2).bookmarks, set([]))
        rev7 = self.master.revision("iwd-8.0.003").node
        self.assertTrue("iwd-8.0.003" in self.slave.revision(rev7).bookmarks)
        self.assertFalse("iwd-8.0.003@default" in self.master.hg_bookmarks().keys())
        self.assertFalse("iwd-8.0.003@default" in self.slave.hg_bookmarks().keys())
        self.assertEqual(self.master.revision(rev3).bookmarks, set([]))
        self.assertEqual(self.slave.revision(rev3).bookmarks, set([]))
        self.assertTrue("iwd-8.1.101" in self.master.revision(rev4).bookmarks)
        self.assertTrue("iwd-8.1.101" in self.slave.revision(rev4).bookmarks)
        self.assertEqual(self.master.revision(rev5).bookmarks, set([]))
        self.assertEqual(self.slave.revision(rev5).bookmarks, set([]))
        self.assertTrue("iwd-8.5.000" in self.master.revision(rev6).bookmarks)
        self.assertTrue("iwd-8.5.000" in self.slave.revision(rev6).bookmarks)


if __name__ == "__main__":
    unittest.main()
