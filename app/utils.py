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
    reviews = Review.query.filter(Review.status == "ACTIVE")
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


def get_new(repo):
    heads = [repo.revision(node) for node in repo.hg_heads()]
    active = [changeset.sha1 for changeset in get_active_changesets()]
    abandoned = set([changeset.sha1 for changeset in
                    Changeset.query.filter(Changeset.status == "ABANDONED")])
    ignored_bookmarks = app.config["IGNORED_BRANCHES"] | \
                        app.config["PRODUCT_BRANCHES"]

    result = []
    for h in heads:
        if h.bookmarks & ignored_bookmarks:
            continue
        if h.node in abandoned:
            continue
        if is_descendant(repo, h.node, active):
            continue
        result.append(h)

    return result


def get_reworks(repo, review):
    if review.status != "ACTIVE":
        return []
    active = review.active_changeset()
    if active is None:
        return []

    heads = [repo.revision(node) for node in repo.hg_heads()]
    changesets = set([changeset.sha1 for changeset in Changeset.query.all()])
    ignored_bookmarks = app.config["IGNORED_BRANCHES"] | \
                        app.config["PRODUCT_BRANCHES"]

    result = []
    for head in heads:
        if head.bookmarks & ignored_bookmarks:
            continue
        if head.node in changesets:
            continue
        if not is_descendant(repo, head.node, [active.sha1]):
            continue
        result.append(head)
    return result


def el(set_):
    l = list(set_)
    if len(l) == 0:
        return None
    else:
        return l[0]


