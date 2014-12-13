import logging

from app import db
from app import repo
from app import jenkins
from app import cc
from app.model import Build, CodeInspection, Diff
from app.utils import known_build_numbers, DatabaseGuard, AbortThread
from app.locks import repo_read
from app.perfutils import performance_monitor

logger = logging.getLogger()

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


# Schedule CodeCollaborator
@repo_read
@performance_monitor("schedule_cc")
def schedule_cc():
    inspections = CodeInspection.query.filter(
        CodeInspection.status == "SCHEDULED").all()
    for i in inspections:
        with DatabaseGuard():
            i.status = "CREATING"
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
            raise AbortThread()
        with DatabaseGuard():
            i.status = "NEW"

    # CC diffs
    diffs = Diff.query.filter(Diff.status == "SCHEDULED").all()
    for d in diffs:
        try:
            logger.info("Processing diff: %d", d.id)
            i = d.changeset.review.inspection
            if i.number is None:
                logger.error("Inspection of diff %d is still scheduled", d.id)
                raise AbortThread()
        except:
            logger.exception("Exception when checking inspection status for diff %d", d.id)
            raise AbortThread()
        with DatabaseGuard():
            d.status = "UPLOADING"
        try:
            if not cc.upload_diff(i.number, d.root, d.changeset.sha1):
                logger.error("Diff %d upload failed", d.id)
                raise AbortThread()
        except:
            logger.exception("Exception when uploading diff: %d", d.id)
            raise AbortThread()
        with DatabaseGuard():
            d.status = "UPLOADED"

    # Update status
    inspections = CodeInspection.query.filter(
        CodeInspection.status != "Completed").filter(
        CodeInspection.status != "Unknown").all()
    for i in inspections:
        try:
            status = cc.fetch_status(i.number)
            logger.info("Updating status of review %d from %s to %s", i.number, i.status, status)
            with DatabaseGuard():
                i.status = status
        except:
            logger.exception("Exception when updating status of inspection %d", i.number)
            logger.info("Updating status of review %d from %s to Unknown", i.number, i.status)
            with DatabaseGuard():
                i.status = "Unknown"
