import os
import tempfile

from proboscis import test, before_class, after_class
from proboscis.asserts import assert_is_not_none
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


@test
class JenkinsTest:

    @before_class
    def setup(self):
        self.app = app.test_client()
        db_create()

    @after_class
    def tear_down(self):
        pass

    @test
    def run_job_exceptions(self):
        with HTTMock(jenkins_next_build_number, jenkins_schedule_error):
            result = jenkins.run_job("iwd-8.5.000-ci", "100")
        assert_is_not_none(result)


def run_tests():
    from proboscis import TestProgram
    TestProgram().run_and_exit()

if __name__ == "__main__":
    run_tests()
