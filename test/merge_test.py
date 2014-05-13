import os

from proboscis import test, before_class
from proboscis.asserts import fail, assert_true, assert_false, assert_raises,\
    assert_equal

from app.hgapi.hgapi import HgException
from app.mercurial import MergeConflictException
from test.mercurial import config, REPO_MASTER, MercurialBase

FILE_3 = os.path.join(config.REPO_PATH, "file2.txt")


@test
class MergeTest(MercurialBase):

    @test
    def failed_push_recovery(self):
        self.init_repos()
        self.commit_master("Initial creation")
        rev1 = self.commit_master("Last commit in official repo", bmk="iwd-8.5.000")
        self.slave.hg_pull()
        rev2 = self.commit_slave("Non-pushed commit in local repo")
        self.slave.hg_sync()
        assert_true("iwd-8.5.000" in self.master.revision(rev2).bookmarks)
        assert_true("iwd-8.5.000" in self.slave.revision(rev2).bookmarks)
        # TODO: Report this situation

    @test
    def advance_branch_recovery(self):
        self.init_repos()
        self.commit_master("Initial creation")
        rev1 = self.commit_master("Last commit in both repos", bmk="iwd-8.5.000")
        self.slave.hg_pull()
        rev2 = self.commit_master("Advance commit in official repo")
        self.slave.hg_sync()
        assert_true("iwd-8.5.000" in self.master.revision(rev2).bookmarks)
        assert_true("iwd-8.5.000" in self.slave.revision(rev2).bookmarks)
        # TODO: Report this situation for official branch

    @test
    def conflicting_changes_during_sync(self):
        self.init_repos()
        self.commit_master("Initial creation", bmk="iwd-8.5.000")
        self.slave.hg_pull()
        rev1 = self.commit_master("Conflicting change in master")
        rev2 = self.commit_slave("Conflicting change in slave")
        try:
            self.slave.hg_sync()
            fail("conflicting changes during sync didn't raise exception")
        except MergeConflictException, ex:
            pass
        else:
            fail("Exception raised, but not MergeConflict.")
        assert_true("iwd-8.5.000" in self.master.revision(rev1).bookmarks)
        assert_raises(HgException, self.master.revision, rev2)
        assert_true("iwd-8.5.000" in self.slave.revision(rev2).bookmarks)
        assert_raises(HgException, self.slave.revision, rev1)
        # TODO: Report this situation

    @test
    def diverged_branches_recovery(self):
        self.init_repos()
        self.commit_master("Initial creation", bmk="iwd-8.5.000")
        self.slave.hg_pull()
        rev1 = self.commit_master("Non-conflicting change in master")
        rev2 = self.commit_slave("Non-conflicting change in slave",
                                 file_name=FILE_3)
        self.slave.hg_sync()
        assert_equal(self.master.revision(rev1).bookmarks, [])
        assert_equal(self.master.revision(rev2).bookmarks, [])
        assert_equal(self.slave.revision(rev1).bookmarks, [])
        assert_equal(self.slave.revision(rev2).bookmarks, [])
        rev3 = self.master.revision("iwd-8.5.000")
        assert_true("iwd-8.5.000" in self.slave.revision(rev3).bookmarks)
        assert_false("iwd-8.5.000@1" in self.master.hg_bookmarks().keys())
        assert_false("iwd-8.5.000@1" in self.master.hg_bookmarks().keys())
        #TODO: Report this situation

    @test
    def multiple_failed_branches(self):
        self.init_repos()
        self.commit_master("Initial creation")
        self.commit_master("Non-conflicting merge root", bmk="iwd-8.0.003")
        self.commit_master("Rogue commit root", bmk="iwd-8.0.101")
        rev5 = self.commit_master("Failed push root", bmk="iwd-8.5.000")
        rev3 = self.commit_master("Official commit", rev="iwd-8.0.101")
        self.slave.hg_pull()
        rev1 = self.commit_master("Official non-conflicting commit",
                                  rev="iwd-8.0.003")
        rev2 = self.commit_slave("Rogue non-conflicting commit",
                                 rev="iwd-8.0.003", file_name=FILE_3)
        rev4 = self.commit_master("Rogue commit", rev="iwd-8.1.101")
        rev6 = self.commit_slave("Official non-pushed commit",
                                 rev="iwd-8.5.000")
        self.slave.hg_sync()
        assert_equal(self.master.revision(rev1).bookmarks, [])
        assert_equal(self.slave.revision(rev1).bookmarks, [])
        assert_equal(self.master.revision(rev2).bookmarks, [])
        assert_equal(self.slave.revision(rev2).bookmarks, [])
        rev7 = self.master.revision("iwd-8.0.003")
        assert_true("iwd-8.0.003" in self.slave.revision(rev7).bookmarks)
        assert_false("iwd-8.0.003@1" in self.master.hg_bookmarks().keys())
        assert_false("iwd-8.0.003@1" in self.slave.hg_bookmarks().keys())
        assert_equal(self.master.revision(rev3).bookmarks, [])
        assert_equal(self.slave.revision(rev3).bookmarks, [])
        assert_true("iwd-8.1.101" in self.master.revision(rev4).bookmarks)
        assert_true("iwd-8.1.101" in self.slave.revision(rev4).bookmarks)
        assert_equal(self.master.revision(rev5).bookmarks, [])
        assert_equal(self.slave.revision(rev5).bookmarks, [])
        assert_true("iwd-8.5.000" in self.master.revision(rev6).bookmarks)
        assert_true("iwd-8.5.000" in self.slave.revision(rev6).bookmarks)
        #TODO: Check, that all violations were reported.


def run_tests():
    from proboscis import TestProgram
    TestProgram().run_and_exit()

if __name__ == "__main__":
    run_tests()
