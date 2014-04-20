import json
import requests
import urllib
from uuid import uuid4
import time


class Jenkins(object):
    def __init__(self, url, app, repo):
        self.url = url
        self.app = app
        self.repo = repo


    def get_next_build_number(self, job_name):
        resp = requests.get(self.url + "/job/" + job_name + "/api/python?pretty=true")
        props = eval(resp.content)
        self.app.logger.debug("Next build number for " + job_name + " is " + str(props["nextBuildNumber"]))
        return props["nextBuildNumber"]

    def run_job(self, job_name, rev):
        build_no = self.get_next_build_number(job_name)
        uuid = str(uuid4())
        info = self.repo.hg_rev_info(rev)
        sha1 = info["changeset_short"]
        payload = urllib.urlencode({
            'token': job_name,
            'json': json.dumps(
                {"parameter": [{"name": "BRANCH", "value": sha1}, {"name": "REQUEST_ID", "value": uuid}]})})
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        resp = requests.post(self.url + "/job/" + job_name + "/build/api/json", data=payload, headers=headers)
        self.app.logger.debug(
            "Scheduling Jenkins job for " + job_name + " using revision " + rev + " Expected build number is " + str(
                build_no))
        if resp.status_code == 201:
            counter = 1
            while counter < 10:
                counter += 1
                # Jenkins queues job and does not start them immediately
                # lets give him some time to respond
                time.sleep(counter)
                resp = requests.get(self.url + "/job/" + job_name + "/" + str(build_no) + "/api/python", data=payload,
                                    headers=headers)
                if resp.status_code != 404:
                    # build has started, make sure we got the right build number (possible race-condition)
                    props = eval(resp.content)
                    for a in props['actions']:
                        if a.has_key("parameters"):
                            for parameters in a['parameters']:
                                if parameters['name'] == "REQUEST_ID" and parameters['value'] == uuid:
                                    self.app.logger.info(
                                        "Successfully scheduled Jenkins job for " + job_name + " using revision " + rev + " url: " +
                                        props["url"])
                                    return {"build_no": build_no, "url": props["url"], "result": None}
                    self.app.logger.error(
                        "Failed job verification, possible race-condition occurred. REQUEST_ID: " + uuid + " jobname: " + job_name + " rev: " + rev + " expected build number: " + str(
                            build_no))
                    return None
        else:
            self.app.logger.error(
                "There was an error scheduling Jenkins job for " + job_name + " using revision " + rev + " Response status code: " + str(resp.status_code) + " , resp content: " + resp.content)
            return None


    def get_build_info(self, job_name, build_no):
        if job_name is None or build_no is None:
            return None
        resp = requests.get(self.url + "/job/" + job_name + "/" + str(build_no) + "/api/python?pretty=true")
        props = eval(resp.content)
        return props

    def get_build_result(self, job_name, build_no):
        res = self.get_build_info(job_name, build_no)
        return res['result'] if res.has_key("result") else None


