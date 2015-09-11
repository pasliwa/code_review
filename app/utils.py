import time
import logging
import threading

from sqlalchemy.sql import desc

from app import jenkins, db, app
from app.model import Build, Changeset
from app.model import Review
from app.view import Pagination
from app.perfutils import performance_monitor

logger = logging.getLogger(__name__)

class AbortThread(Exception): pass

class Anacron(threading.Thread):
    def __init__(self, interval, function, name):
        threading.Thread.__init__(self)
        self.name = name
        self.interval = interval
        self.function = function
        self.interrupted = threading.Event()

    def stop(self):
        self.interrupted.set()

    def run(self):
        while not self.interrupted.is_set():
            logging.info("Executing background job")
            try:
                self.function()
            except AbortThread:
                logging.error("Fatal error in background thread. Aborting.")
                break
            except:
                logging.exception("Exception in background thread")
            delay = self.interval - (time.time() % self.interval)
            logging.info("Sleeping %d s", delay)
            self.interrupted.wait(delay)


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
            logger.exception("Exception in session rollback.")

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error("Exception in DatabaseGuard",
                         exc_info=(exc_type, exc_val, exc_tb))
            raise AbortThread()
        self.__session_commit()


#TODO: Move to model
def known_build_numbers(job_name):
    query = db.session.query(Build.build_number)\
        .filter(Build.job_name == job_name)\
        .filter(Build.build_number != None)
    return [int(row.build_number) for row in query.all()]


def get_reviews(status, page, request):
    if status == "ACTIVEandCONFLICT":
        f = Review.query.filter((Review.status == "ACTIVE") | (Review.status == "CONFLICT"))
    else:
        f = Review.query.filter(Review.status == status)
    author = request.args.get('author', None)
    title = request.args.get('title', None)
    if author:
        f = f.filter((Review.owner.contains(author)))
    if title:
        f = f.filter((Review.title.contains(title)))
    if status == "MERGED":
        query = f.order_by(desc(Review.close_date)).paginate(page, app.config["PER_PAGE"], False)
    else:
        query = f.order_by(desc(Review.created_date)).paginate(page, app.config["PER_PAGE"], False)
    total = query.total
    reviews = query.items
    pagination = Pagination(page, app.config["PER_PAGE"], total)
    return {"r": reviews, "p": pagination}


def get_active_changesets():
    reviews = Review.query.filter((Review.status == "ACTIVE") | (Review.status == "CONFLICT"))
    changesets = []
    for review in reviews:
        for changeset in review.changesets:
            if changeset.status == "ACTIVE":
                changesets.append(changeset)
                break
    return changesets


def is_descendant(repo, node, parents):
    for chset in parents:
        if repo.hg_ancestor(node, chset) == chset:
            return True
    return False


def get_parents(repo, node, candidates):
    result = []
    for chset in candidates:
        if repo.hg_ancestor(node, chset) == chset:
            result.append(chset)
    return result


def get_revision_status(repo, revision):
    heads = repo.hg_heads()
    active = [changeset.sha1 for changeset in get_active_changesets()]
    changesets = set([changeset.sha1 for changeset in Changeset.query.all()])
    abandoned = set([changeset.sha1 for changeset in
                    Changeset.query.filter(Changeset.status == "ABANDONED")])
    product_bookmarks = app.config["PRODUCT_BRANCHES"]
    ignored_bookmarks = app.config["IGNORED_BRANCHES"]

    if revision.bookmarks & product_bookmarks:
        return "merged"
    if revision.bookmarks & ignored_bookmarks:
        return "ignored"
    if revision.node not in heads:
        return "not head"
    if revision.node in abandoned:
        return "abandoned"
    if revision.node in changesets:
        return "changeset"
    if is_descendant(repo, revision.node, active):
        return "rework"
    return "new"



def get_heads(repo):
    heads = [repo.revision(node) for node in repo.hg_heads()]
    active = dict([(changeset.sha1, changeset) for changeset in get_active_changesets()])
    changesets = set([changeset.sha1 for changeset in Changeset.query.all()])
    abandoned = set([changeset.sha1 for changeset in
                    Changeset.query.filter(Changeset.status == "ABANDONED")])
    ignored_bookmarks = app.config["IGNORED_BRANCHES"] | \
                        app.config["PRODUCT_BRANCHES"]
    result = []
    for head in heads:
        if head.bookmarks & ignored_bookmarks:
            continue
        if head.node in abandoned:
            continue
        if head.node in changesets:
            continue
        parents = get_parents(repo, head.node, active.keys())
        if parents:
            if len(parents) > 1:
                logger.warning("Head %s has multiple parents: ", head.node, ", ".join(parents))
            head.review_id = active[parents[0]].review_id
            head.targets = []
        else:
            head.review_id = None
            head.targets = repo.hg_targets(head.node, app.config["PRODUCT_BRANCHES"])
        result.append(head)
    return result


def el(set_):
    l = list(set_)
    if len(l) == 0:
        return None
    else:
        return l[0]


