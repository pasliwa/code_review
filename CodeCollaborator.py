import os
import re
import subprocess
import config


class CodeCollaborator(object):
    def create_empty_cc_review(self):
        """

        @rtype : String
        """
        print config.CC_BIN
        output = subprocess.check_output(
            "{cc} --no-browser --non-interactive admin review create".format(cc=config.CC_BIN), shell=True)
        output2 = """'Connecting to CodeCollaborator Server http://rd-w2k8.us.int.genesyslab.com:9090
    Connected as: Roman Szalla (roman.szalla)
    Creating new review.
    New review created: Review #33327: "Untitled Review".
    '"""
        regex = re.compile("Review #([0-9]+)")
        r = regex.search(output)
        reviewId = r.groups()[0]
        return reviewId

    def upload_diff(self, reviewId, revision, repoPath):
        curr = os.getcwd()
        print os.getcwd()
        revision = int(revision)
        output = subprocess.check_output(
            "{cc} addhgdiffs {reviewId} -r {rev1} -r {rev2}".format(cc=config.CC_BIN, reviewId=reviewId,
                                                                    rev1=revision - 1, rev2=revision), cwd=repoPath, shell=True)
        if "Changes successfully attached" in output:
            return (True, output)
        return (False, output)


