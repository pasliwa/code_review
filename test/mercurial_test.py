import os
import os.path
import shutil
import logging
import unittest

from dingus import patch, Dingus

from sandbox import REPO_MASTER, config

import flask.templating
from app import app, db
from app.model import Changeset
from db_create import db_create

from test.mercurial import MercurialBase, FILE_3



class MercurialTest(MercurialBase):

    def login(self, username, password):
        return self.app.post('/login', data=dict(
            email=username,
            password=password
        ), follow_redirects=True)

    def logout(self):
        return self.app.get('/logout', follow_redirects=True)

    # Disable docstring printing
    def shortDescription(self):
        return None

    def setUp(self):
        if os.path.exists(REPO_MASTER):
            shutil.rmtree(REPO_MASTER)
        if os.path.exists(config.REPO_PATH):
            shutil.rmtree(config.REPO_PATH)
        db_create()
        self.app = app.test_client()
        self.init_repos()
        self.commit_master("Initial creation",   tag="root")
        self.commit_master("IWD 8.0 root",       tag="b800",        rev="root")
        self.commit_master("IWD 8.0.001 branch", bmk="iwd-8.0.001", rev="b800")
        self.commit_master("IWD 8.0.002 root",   tag="b801",        rev="b800")
        self.commit_master("IWD 8.0.002 branch", bmk="iwd-8.0.002", rev="b801")
        self.commit_master("IWD 8.0.003 branch", bmk="iwd-8.0.003", rev="b801")
        self.commit_master("IWD 8.5.000 root",   tag="b810",        rev="root")
        self.commit_master("IWD 8.1 root",       tag="b811",        rev="b810")
        self.commit_master("IWD 8.1.000 branch", bmk="iwd-8.1.000", rev="b811")
        self.commit_master("IWD 8.1.001 branch", bmk="iwd-8.1.001", rev="b811")
        self.commit_master("IWD 8.1.101 branch", bmk="iwd-8.1.101", rev="b811")
        self.commit_master("IWD 8.5.000 branch", bmk="iwd-8.5.000", rev="b810")
        self.slave.hg_pull()

    def tearDown(self):
        db.drop_all()

    def detektyw_login(self):
        """ Login into Detektyw """
        rv = self.login("maciej.malycha@genesyslab.com", "password")
        self.assertTrue("Active changes" in rv.data)

    def review_open(self, node):
        """ Open new review """
        with patch("flask.templating._render", Dingus(return_value='')):
            rv = self.app.post("/review", data={"node": node},
                               follow_redirects=True)
            cs = flask.templating._render.calls[0].args[1]['cs']
        return cs.id

    def review_merge(self, cs_id):
        """ Merge review """
        # TODO: Review should be merged, not changeset
        rv = self.app.post("/changeset/%d/merge" % cs_id, data={},
                           follow_redirects=True)
        return rv.data

    def review_get(self, id):
        with patch("flask.templating._render", Dingus(return_value='')):
            rv = self.app.get("/review/%d" % id)
            review = flask.templating._render.calls[0].args[1]['review']
        return review

    def rework_list(self):
        """ Get list of reworks for first review """
        #TODO: Separate refresh method
        self.app.get("/changes/refresh")
        with patch("flask.templating._render", Dingus(return_value='')):
            rv = self.app.get("/review/1")
            revisions = flask.templating._render.calls[0].args[1]['descendants']
        return revisions

    def rework_create(self, node):
        """ Create new rework """
        self.app.post("/review/1", data={"node": node})

    def changeset_abandon(self, cid):
        self.app.post("/changeset/%d/abandon" % cid, data={})

    def new_list(self):
        """ Get list of new review candidates """
        self.app.get("/changes/refresh")
        with patch("flask.templating._render", Dingus(return_value='')):
            rv = self.app.get("/changes/new")
            revisions = flask.templating._render.calls[0].args[1]['revisions']
        return revisions

    def test_recognize_reworks(self):
        """Push chain of two commits and one commit, both lines originating
           from active changeset
            - Verify, that both are qualified as reworks
            - Choose one and create changeset
            - Verify, that other one is moved to 'New'
        """
        # Commit new revision IWD-0005 on top of iwd-8.0.003
        rev = self.commit_master("IWD-0005: Reworks parent", bmk="IWD-0005",
                                 rev="iwd-8.0.003")
        parent_node = self.master.revision(rev).node
        self.detektyw_login()
        self.review_open(parent_node)
        # Commit new revision and chain of two revisions on top of IWD-0005
        self.commit_master("IWD-0005: Rework 1.0", bmk="rev1")
        self.commit_master("IWD-0005: Rework 1.1")
        self.commit_master("IWD-0005: Rework 2.0", bmk="rev2", rev="IWD-0005")
        # Verify, that they don't show up as new changes
        self.assertEqual(len(self.new_list()), 0)
        # But show up as reworks
        revisions = self.rework_list()
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0].title, "IWD-0005: Rework 2.0")
        self.assertEqual(revisions[1].title, "IWD-0005: Rework 1.1")
        # Create new changeset out of one revision
        self.rework_create(revisions[1].node)
        # Verify, that second one is not rework candidate
        #TODO: Check if full chain of revisions is sent to collaborator
        #TODO: Test both cases also without refresh
        self.assertEqual(len(self.rework_list()), 0)
        # But new revision
        revisions = self.new_list()
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].title, "IWD-0005: Rework 2.0")

    def test_revision_from_old_changeset(self):
        """Push revision originating from older changeset
            - Verify, that it appears on 'New'
            - Abandon active changeset
            - Verify, that commit becomes rework candidate
        """
        # Commit new revision IWD-0006 on top of iwd-8.1.001
        self.commit_master("IWD-0006: Older changeset", bmk="IWD-0006",
                           rev="iwd-8.1.001")
        self.detektyw_login()
        # Verify, that IWD-0006 revision is on list of new revisions
        revisions = self.new_list()
        self.assertEqual(len(revisions), 1)
        self.assertTrue(revisions[0].title.startswith("IWD-0006"))
        review_sha1 = revisions[0].node
        self.review_open(review_sha1)
        # Commit new revision on top of IWD-0006
        self.commit_master("IWD-0006: Newer changeset")
        # Verify, that it shows up as rework
        revisions = self.rework_list()
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].title, "IWD-0006: Newer changeset")
        rework_sha1 = revisions[0].node
        # Make it changeset
        self.rework_create(rework_sha1)
        # Commit new revision on top of older changeset
        self.commit_master("IWD-0006: Side branch", rev=review_sha1)
        # Verify, that it is on list of new revisions
        revisions = self.new_list()
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].title, "IWD-0006: Side branch")
        # But not on the review list
        self.assertEqual(len(self.rework_list()), 0)
        # Abandon active changeset
        rework_changeset = Changeset.query.filter(Changeset.sha1 == rework_sha1).first()
        self.changeset_abandon(rework_changeset.id)
        # Verify, that side branch is not on new
        self.assertEqual(len(self.new_list()), 0)
        # But listed as rework
        revisions = self.rework_list()
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].title, "IWD-0006: Side branch")

    def test_dangling_heads(self):
        """Merge review with dangling heads (true merge)
            - Verify, that last active review is merged
            - Verify, that dangling heads became new
            - Verify, that heads no longer appear as rework candidates
        """
        # Commit new revision IWD-0009 on top of iwd-8.5.000
        self.commit_master("IWD-0009: Dangling branches root", bmk="IWD-0009",
                           rev="iwd-8.5.000")
        head_id = self.commit_master("IWD-1009: Advance branch for true merge",
                                     bmk="iwd-8.5.000", rev="iwd-8.5.000",
                                     file_name=FILE_3)
        self.detektyw_login()
        # Verify, that IWD-0009 revision is on list of new revisions
        revisions = self.new_list()
        self.assertEqual(len(revisions), 1)
        self.assertTrue(revisions[0].title.startswith("IWD-0009"))
        review_sha1 = revisions[0].node
        cs_id = self.review_open(review_sha1)
        # Commit two rework branches to IWD-0009
        self.commit_master("IWD-0009: Rework 1.0", bmk="rev1", rev="IWD-0009")
        self.commit_master("IWD-0009: Rework 1.1")
        self.commit_master("IWD-0009: Rework 2.0", bmk="rev2", rev="IWD-0009")
        # Verify, that they don't show up as new changes
        self.assertEqual(len(self.new_list()), 0)
        # But show up as reworks
        self.assertEqual(len(self.rework_list()), 2)
        # Merge IWD-0009 but not the reworks
        self.review_merge(cs_id)
        # Verify, that merge, commit and push was done
        self.assertFalse("iwd-8.5.000" in self.slave.revision(review_sha1).bookmarks)
        self.assertFalse("iwd-8.5.000" in self.slave.revision(head_id).bookmarks)
        self.assertFalse("iwd-8.5.000" in self.master.revision(review_sha1).bookmarks)
        self.assertFalse("iwd-8.5.000" in self.master.revision(head_id).bookmarks)
        # Verify, that reworks show up on new
        revisions = self.new_list()
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0].title, "IWD-0009: Rework 2.0")
        self.assertEqual(revisions[1].title, "IWD-0009: Rework 1.1")
        # But not on the review page
        self.assertEqual(len(self.rework_list()), 0)

    def test_diverged_merge(self):
        """Merge review with conflicting changes (diverged)
            - Verify, that merge is not done
            - Verify, that local repository is recovered
            - Verify, that user is informed
        """
        # Commit two new revisions IWD-0010 on top of iwd-8.0.002
        rev1 = self.commit_master("IWD-1010: Diverged merge 1", bmk="IWD-1010",
                                  rev="iwd-8.0.002")
        rev1_node = self.master.revision(rev1).node
        rev2 = self.commit_master("IWD-2010: Diverged merge 2", bmk="IWD-2010",
                                  rev="iwd-8.0.002")
        rev2_node = self.master.revision(rev2).node
        self.detektyw_login()
        # Open review for first revision and merge it
        cs_id = self.review_open(rev1_node)
        self.review_merge(cs_id)
        # Open review for second revision and try to merge it
        cs_id = self.review_open(rev2_node)
        rv_data = self.review_merge(cs_id)
        # Verify, that user is informed
        self.assertTrue("There is merge conflict. Merge with bookmark "
                    "iwd-8.0.002 and try again." in rv_data)
        # Verify, that merge is not done
        self.assertTrue("iwd-8.0.002" in self.master.revision(rev1_node).bookmarks)
        self.assertTrue("iwd-8.0.002" in self.slave.revision(rev1_node).bookmarks)
        self.assertEqual(self.review_get(2).status, "ACTIVE")
        # Verify, that repository has recovered
        for key, value in self.slave.hg_status().items():
            self.assertEqual(value, [])
        self.assertEqual(self.slave.hg_id(), "000000000000")

    def test_merge_with_ancestor(self):
        """Merge review with official branch being descendant of active
           changeset (merging with ancestor case)
            - Verify, that official branch is not recognized as rework
            - Verify, that merge is correctly done
        """
        # Commit new revision IWD-0012 on top of iwd-8.1.101
        rev = self.commit_master("IWD-0012: Merge with ancestor",
                                 bmk="IWD-0012", rev="iwd-8.1.101")
        parent_node = self.master.revision(rev).node
        self.detektyw_login()
        parent_cs_id = self.review_open(parent_node)
        # Add new commit and move official branch there
        rev = self.commit_master("IWD-0012: Descendant being official branch",
                                 bmk="iwd-8.1.101")
        child_node = self.master.revision(rev).node
        # Verify, that official branch is not recognized as rework
        self.assertEqual(len(self.rework_list()), 0)
        # And can be merged without problem
        self.review_merge(parent_cs_id)
        # Review is merged
        self.assertEqual(self.review_get(1).status, "MERGED")
        # And official bookmark didn't move
        child_revision = self.master.revision(child_node)
        self.assertTrue("iwd-8.1.101" in child_revision.bookmarks)


if __name__ == "__main__":
    unittest.main()
