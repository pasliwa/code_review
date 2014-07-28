#!/usr/bin/python26

activate_this = '/home/ci_test/virtualenv/code_review/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))


import time
import logging
import threading

from app import app
from app import db
from app import repo
from app import logs
from app import jenkins
from app import cc
from app.model import Build, CodeInspection, Diff
from app.utils import known_build_numbers
from app.perfutils import performance_monitor

logger = logging.getLogger()

class AbortThread(Exception): pass

class Anacron(threading.Thread):
    def __init__(self, interval, function, title):
        self.title = title
        self.interval = interval
        self.function = function

    def run(self):
        while True:
            try:
                self.function()
            except AbortThread:
                logging.error("Fatal error in thread %s. Aborting thread.",
                              self.title)
                break
            except:
                logging.exception("Exception in " + self.title)
            delay = time.time() % self.interval
            time.sleep(delay)


class DatabaseGuard:

    def __session_commit(self):
        try:
            db.session.commit()
        except:
            logger.exception("Exception in session commit. "
                             "Rollback and kill thread.")
            self.__session_rollback()
            raise AbortThread()

    def __session_rollback(self):
        try:
            db.session.rollback()
        except:
            logger.exception

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type != None:
            logger.error("Exception in DatabaseGuard",
                         exc_info=(exc_type, exc_val, exc_tb))
            raise AbortThread()
        try:
            db.session.commit()
        except:
            logger.exception("Exception in session commit")
            try:
                db.session.rollback()
            except:
                logger.exception("Exception in session rollback")
            raise AbortThread()

@performance_monitor("update_mercurial")
def update_mercurial():
    repo.hg_sync()


@performance_monitor("update_jenkins")
def update_jenkins():
    builds = Build.query.filter(Build.status.in_(["Queued", "Running"])).all()
    for build in builds:
        logger.info("Updating build status for build %d", build.id)
        if build.build_number is not None:
            build.status = jenkins.get_build_status(build.job_name,
                                                    build.build_number)
            logger.debug("Build %d with status %s", build.build_number,
                         build.status)
        elif jenkins.check_queue(build.job_name, build.request_id):
            build.status = "Queued"
            logger.debug("Build is queued")
        else:
            new_builds = set(jenkins.list_builds(build.job_name)) - \
                set(known_build_numbers(build.job_name))
            for build_number in new_builds:
                build_info = jenkins.get_build_info(build.job_name, build_number)
                if build_info["request_id"] == build.request_id:
                    build.status = build_info["status"]
                    build.build_number = build_number
                    build.build_url = build_info["build_url"]
                    logger.debug("Build found with number %d and status %s",
                                 build.build_number, build.status)
                    break
            else:
                logger.warning("Build %d is missing", build.id)
                build.status = "Missing"
        db.session.commit()


@performance_monitor("schedule_jenkins")
def schedule_jenkins():
    builds = Build.query.filter(Build.status == "SCHEDULED").all()
    for b in builds:
        try:
            logger.info("Processing build: %d", b.id)
            build_info = jenkins.run_job(b.job_name, b.changeset.sha1)
            if build_info is None:
                logger.error("Build id " + str(b.id) + " has been skipped.")
                continue
        except:
            logger.exception("Exception when running build: %d", b.id)
            continue
        try:
            b.status = build_info["status"]
            b.request_id = build_info["request_id"]
            b.scheduled = build_info["scheduled"]
            b.build_url = build_info["build_url"]
            if "build_number" in build_info:
                b.build_number = build_info["build_number"]
            db.session.commit()
        except:
            logger.exception("Exception when updating Build record %d", b.id)
            try:
                db.session.rollback()
            except:
                logger.exception("Exception during Build record rollback")
            raise AbortThread()


# Schedule CodeCollaborator
@performance_monitor("schedule_cc")
def schedule_cc():
    inspections = CodeInspection.query.filter(
        CodeInspection.status == "SCHEDULED").all()
    for i in inspections:
        try:
            logger.info("Processing inspection: %d", i.id)
            if i.number is not None:
                logger.error("Inspection %d with number is still scheduled.",
                             i.id)
                continue
            i.number, i.url = cc.create_review(i.review.title, i.review.target)
            if i.number is None:
                logger.error("Creating inspection %d in CodeCollaborator "
                             "failed.", i.id)
                continue
            cc.add_participant(i.number, i.author, "author")
        except:
            logger.exception("Exception when processing inspection: %d", i.id)
            continue
        try:
            i.status = "NEW"
            db.session.commit()
        except:
            logger.exception("Exception when updating CodeInspection %d", i.id)
            try:
                db.session.rollback()
            except:
                logger.exception("Exception during CodeInspection record rollback")
            raise AbortThread()

    # CC diffs
    diffs = Diff.query.filter(Diff.status == "SCHEDULED").all()
    for d in diffs:
        try:
            logger.info("Processing diff: %d", d.id)
            i = d.changeset.review.inspection
            if i.status == "SCHEDULED":
                logger.error("Inspection of diff %d is still scheduled", d.id)
                continue
            if cc.upload_diff(i.number, i.root, d.changeset.sha1):
                d.status = "UPLOADED"
                db.session.commit()
        except:
            logger.exception("Exception when uploading diff: %d", d.id)
            db.session.rollback()




if __name__ == '__main__':
    logging.getLogger().setHandler(logs.get_mail_handler())
    logging.getLogger().setHandler(logs.get_file_handler("background.log"))
    Anacron(60, update_mercurial).start()