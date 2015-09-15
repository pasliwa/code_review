import logging
import datetime
from uuid import uuid4

import jenkinsapi

from app.perfutils import performance_monitor

logger = logging.getLogger(__name__)

class Jenkins(object):
    def __init__(self, url):
        self.url = url
        self.api = jenkinsapi.jenkins.Jenkins(self.url, lazy=True)

    def run_job(self, job_name, node):
        if not self.api.has_job(job_name):
            logger.error("Cannot find job %s", job_name)
            return None
        job = self.api.get_job(job_name)

        if not job.is_enabled():
            logger.error("Project %s is disabled.", job_name)
            return "DISABLED"
            
        uuid = str(uuid4())
        parameters = {"BRANCH": node, "REQUEST_ID": uuid}

        logger.info("Invoking job %s for revision %s with id %s",
                    job_name, node, uuid)
        invocation = job.invoke(securitytoken=job_name, build_params=parameters)

        if invocation.is_queued():
            logger.info("Build %s is queued in job %s", uuid, job_name)
            return {"status": "Queued",
                    "request_id": uuid,
                    "scheduled": datetime.datetime.utcnow(),
                    "build_url": self.url + "/job/" + job_name}

        if invocation.is_running():
            build_number = invocation.get_build_number()
            logger.info("Build %s running in job %s with number %d",
                        uuid, job_name, build_number)
            return {"status": "Running",
                    "request_id": uuid,
                    "scheduled": datetime.datetime.utcnow(),
                    "build_number": build_number,
                    "build_url": invocation.get_build().get_result_url()}

        logger.error("Build %s is neither queued nor running in job %s",
                     uuid, job_name)
        return None

    @performance_monitor("check_queue")
    def check_queue(self, job_name, request_id):
        if not self.api.has_job(job_name):
            logger.error("Cannot find job %s", job_name)
            return None

        logger.info("Looking for build %s in Jenkins queue", request_id)
        for item in self.api.get_queue().get_queue_items_for_job(job_name):
            params = item.get_parameters()
            if "REQUEST_ID" in params and params["REQUEST_ID"] == request_id:
                logger.info("Found build %s in Jenkins queue", request_id)
                return True
        logger.info("Build %s is no longer in Jenkins queue", request_id)
        return False

    @performance_monitor("list_builds")
    def list_builds(self, job_name):
        if not self.api.has_job(job_name):
            logger.error("Cannot find job %s", job_name)
            return None
        return self.api.get_job(job_name).get_build_ids()

    def __get_build_status(self, build):
        if build is None:
            return "Missing"
        elif build.is_running():
            return "Running"
        else:
            return build.get_status()

    def __get_build_request_id(self, build):
        if build is None:
            return None
        actions = build.get_actions()
        if not 'parameters' in actions:
            return None
        for param in actions['parameters']:
            if param['name'] == 'REQUEST_ID':
                return param['value']

    def __get_build_url(self, build):
        if build is None:
            return None
        return "%s/job/%s/%d/" % (self.url, build.job, build.get_number())

    def __get_build(self, job_name, build_number):
        if not self.api.has_job(job_name):
            logger.error("Cannot find job %s", job_name)
            return None

        logger.info("Fetching build %s:%d", job_name, build_number)
        job = self.api.get_job(job_name)
        try:
            # jenkinsapi requires int here; SQLAlchemy returns long
            return job.get_build(int(build_number))
        except KeyError:
            # Sometimes after Jenikins restart, job just disappears
            return None

    @performance_monitor("get_build_status")
    def get_build_status(self, job_name, build_number):
        build = self.__get_build(job_name, build_number)
        status = self.__get_build_status(build)
        logger.info("Build %s:%d status is %s", job_name, build_number, status)
        return status

    @performance_monitor("get_build_info")
    def get_build_info(self, job_name, build_number):
        build = self.__get_build(job_name, build_number)
        result = {"status": self.__get_build_status(build),
                  "request_id": self.__get_build_request_id(build),
                  "build_url": self.__get_build_url(build)}
        logger.info("Build %s:%d status %s, request_id %s", job_name,
                    build_number, result["status"], result["request_id"])
        return result


