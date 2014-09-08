import unittest
from httmock import urlmatch, HTTMock

import config
config.SQLALCHEMY_DATABASE_URI = "sqlite://"
config.TESTING = True

from app import app, jenkins
from db_create import db_create


@urlmatch(netloc="pl-byd-srv01.emea.int.genesyslab.com",
          path="/jenkins_test/job/iwd-8.5.000-ci/api/python")
def jenkins_next_build_number(url, request):
    return {"status_code": 200,
            "content": "{'nextBuildNumber': 10}"}

@urlmatch(netloc="pl-byd-srv01.emea.int.genesyslab.com",
          path="/jenkins_test/job/iwd-8.5.000-ci/build/api/json")
def jenkins_schedule_error(url, request):
    return {"status_code": 500, "content": "\xc2".encode("utf-8")}


class JenkinsTest(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        db_create()

    def run_job_exceptions(self):
        with HTTMock(jenkins_next_build_number, jenkins_schedule_error):
            result = jenkins.run_job("iwd-8.5.000-ci", "100")
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
