import logging

from app.threadutils import RWLock

logger = logging.getLogger(__name__)

repo_lock = RWLock()
rework_lock = RWLock()

def repo_write(fun):
    def wrapper(*args, **kwargs):
        logging.debug("Acquiring repository write lock")
        repo_lock.writer_acquire()
        try:
            return fun(*args, **kwargs)
        finally:
            logging.debug("Releasing repository write lock")
            repo_lock.writer_release()

    result = wrapper
    result.__doc__ = fun.__doc__
    result.__name__ = fun.__name__
    result.__module__ = fun.__module__
    return result

def repo_read(fun):
    def wrapper(*args, **kwargs):
        logging.debug("Acquiring repository read lock")
        repo_lock.reader_acquire()
        try:
            return fun(*args, **kwargs)
        finally:
            logging.debug("Releasing repository read lock")
            repo_lock.reader_release()

    result = wrapper
    result.__doc__ = fun.__doc__
    result.__name__ = fun.__name__
    result.__module__ = fun.__module__
    return result

def rework_db_write(fun):
    def wrapper(*args, **kwargs):
        logging.debug("Acquiring rework database write lock")
        rework_lock.writer_acquire()
        try:
            return fun(*args, **kwargs)
        finally:
            logging.debug("Releasing rework database write lock")
            rework_lock.writer_release()

    result = wrapper
    result.__doc__ = fun.__doc__
    result.__name__ = fun.__name__
    result.__module__ = fun.__module__
    return result

def rework_db_read(fun):
    def wrapper(*args, **kwargs):
        logging.debug("Acquiring rework database read lock")
        rework_lock.reader_acquire()
        try:
            return fun(*args, **kwargs)
        finally:
            logging.debug("Releasing rework database read lock")
            rework_lock.reader_release()

    result = wrapper
    result.__doc__ = fun.__doc__
    result.__name__ = fun.__name__
    result.__module__ = fun.__module__
    return result

