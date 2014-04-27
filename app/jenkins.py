import json
import requests
import urllib
import urlparse
from uuid import uuid4
import time
import datetime

import jenkinsapi

class Jenkins(object):
    def __init__(self, url, app, repo):
        self.url = url
        self.app = app
        self.repo = repo
        self.api = jenkinsapi.jenkins.Jenkins(self.url, lazy=True)

    def run_job(self, job_name, rev):
        if not self.api.has_job(job_name):
            self.app.logger.error("Cannot find job %s", job_name)
            return None
        job = self.api.get_job(job_name)

        info = self.repo.revision(rev)
        #TODO: Missing revision
        sha1 = info.node
        uuid = str(uuid4())
        parameters = {"BRANCH": sha1, "REQUEST_ID": uuid}

        self.app.logger.info("Invoking job %s for revision %s with id %s",
                             job_name, rev, uuid)
        invocation = job.invoke(securitytoken=job_name, build_params=parameters)

        if invocation.is_queued():
            self.app.logger.info("Build %s is queued in job %s", uuid, job_name)
            return {"status": "Queued",
                    "request_id": uuid,
                    "scheduled": datetime.datetime.utcnow(),
                    "build_url": self.url + "/job/" + job_name}

        if invocation.is_running():
            build_number = invocation.get_build_number()
            self.app.logger.info("Build %s running in job %s with number %d",
                                 uuid, job_name, build_number)
            return {"status": "Running",
                    "request_id": uuid,
                    "scheduled": datetime.datetime.utcnow(),
                    "build_number": build_number,
                    "build_url": invocation.get_build().get_result_url()}

        self.app.logger.error("Build %s is neither queued nor running in job %s",
                              uuid, job_name)
        return None

    def check_queue(self, job_name, request_id):
        if not self.api.has_job(job_name):
            self.app.logger.error("Cannot find job %s", job_name)
            return None

        self.app.logger.info("Looking for build %s in Jenkins queue", request_id)
        for item in self.api.get_queue().get_queue_items_for_job(job_name):
            params = item.get_parameters()
            if "REQUEST_ID" in params and params["REQUEST_ID"] == request_id:
                self.app.logger.info("Found build %s in Jenkins queue", request_id)
                return True
        self.app.logger.info("Build %s is no longer in Jenkins queue", request_id)
        return False

    def _get_build_status(self, build):
        if build.is_running():
            return "Running"
        else:
            return build.get_status()

    def find_build(self, job_name, request_id):
        if not self.api.has_job(job_name):
            self.app.logger.error("Cannot find job %s", job_name)
            return None

        self.app.logger.info("Looking for build %s in Jenkins", request_id)
        job = self.api.get_job(job_name)
        for build_id in job.get_build_ids():
            build = job.get_build(build_id)
            for param in build.get_actions()['parameters']:
                if param['name'] == 'REQUEST_ID' and param['value'] == request_id:
                    self.app.logger.info("Found build %d in job %s for id %s",
                                         build.get_number(),
                                         job_name,
                                         request_id)
                    build_number = build.get_number()
                    build_url = "%s/job/%s/%d/" % \
                                (self.url, job_name, build_number)
                    return {"status": self._get_build_status(build),
                            "build_number": build_number,
                            "build_url": build_url}
        self.app.logger.info("Build %s not found in Jenkins job %s",
                             request_id, job_name)
        return None

    def get_build_info(self, job_name, build_number):
        if not self.api.has_job(job_name):
            self.app.logger.error("Cannot find job %s", job_name)
            return None

        self.app.logger.info("Fetching build %d in job %s",
                             build_number, job_name)
        job = self.api.get_job(job_name)
        build = job.get_build(build_number)
        return {"status": self._get_build_status(build)}



