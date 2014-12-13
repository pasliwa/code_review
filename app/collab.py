import logging
import re
import subprocess


logger = logging.getLogger(__name__)


# subprocess.check_output was introduced in 2.7 see
# http://docs.python.org/library/subprocess.html#subprocess.check_output
class CalledProcessError(Exception):
    """This exception is raised when a process run by check_call() or
    check_output() returns a non-zero exit status.
    The exit status will be stored in the returncode attribute;
    check_output() will also store the output in the output attribute.
    """
    def __init__(self, returncode, cmd, output=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
    def __str__(self):
        return "Command '%s' returned non-zero exit status %d" % (self.cmd, self.returncode)

subprocess.CalledProcessError = CalledProcessError

if "check_output" not in dir(subprocess):  # duck punch it in!
    def f(*popenargs, **kwargs):
        if 'stdout' in kwargs:
            raise ValueError(
                'stdout argument not allowed, it will be overridden.')
        process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs,
                                   **kwargs)
        output, unused_err = process.communicate()
        retcode = process.poll()
        if retcode:
            cmd = kwargs.get("args")
            if cmd is None:
                cmd = popenargs[0]
            raise subprocess.CalledProcessError(retcode, cmd, output)
        return output

    subprocess.check_output = f


def bash_escape(text):
    return text.replace("'", "'\"'\"'")


class CodeCollaborator(object):
    def __init__(self, cc_bin, cc_review_url, repo_path):
        self.cc_bin = cc_bin
        self.cc_review_url = cc_review_url
        self.repo_path = repo_path

    def cc_command(self, command, *args):
        cmd = "{cc} --no-browser --non-interactive {cmd} {args}" \
            .format(cc=self.cc_bin, cmd=command, args=' '.join(args))
        logger.info("Executing command: %s", cmd)
        try:
            output = subprocess.check_output(cmd, cwd=self.repo_path,
                                             shell=True)
        except subprocess.CalledProcessError, cpe:
            logger.error("Shell command returned non-zero status:\n"
                         "Command: %s\nOutput: %s\nReturn code: %s",
                         cpe.cmd, cpe.output, cpe.returncode)
            return ""
        logger.debug("Command response: %s", output)
        return output

    def create_review(self, title, target_release):
        output = self.cc_command(
            "admin review create",
            "--custom-field 'Overview=Auto generated by code review tool'",
            "--custom-field 'Project=iWD (Intelligent Workload Distribution)'",
            "--custom-field 'Release={0}'".format(target_release[4:9]),
            "--title '{0}'".format(bash_escape(title)))
        match = re.compile("Review #([0-9]+)").search(output)
        if match:
            review_id = match.groups()[0]
            review_url = self.cc_review_url.format(reviewId=review_id)
            return review_id, review_url
        logger.error('There was an error during inspection creation in '
                     'CodeCollaborator. Command returned: %s',
                     output)
        return None, None

    def add_participant(self, review_id, user_cc_login, role):
        if user_cc_login is None:
            logger.error("The author for review %s is 'None'.", review_id)
            return
        self.cc_command("admin review participant assign",
                        review_id, user_cc_login, role)

    def upload_diff(self, review_id, root, node):
        output = self.cc_command("addhgdiffs", str(review_id),
                                 "-r {0}".format(root),
                                 "-r {0}".format(node))
        if not "Changes successfully attached" in output:
            logger.error('There was an error during upload of diff to '
                         'CodeCollaborator review %s. Command returned: %s',
                         review_id, output)
            return False
        return True

    def fetch_status(self, review_id):
        output = self.cc_command("admin review-xml", str(review_id),
                                 "--xpath '//reviews/review/general/phase/text()")
        return output
