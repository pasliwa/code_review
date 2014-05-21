import time
import logging

# TODO: Move to utils after clean-up
class PerformanceMonitor:

    logger = logging.getLogger("performance")

    def __init__(self, text):
        self.text = text

    def __enter__(self):
        self.milis = int(round(time.time() * 1000))

    def __exit__(self, ex_type, ex_value, ex_traceback):
        delta = int(round(time.time() * 1000)) - self.milis
        self.logger.debug("%s took %d ms", self.text, delta)


def performance_monitor(text):
    def inner(fun):
        def wrapper(*args, **kwargs):
            with PerformanceMonitor(text):
                return fun(*args, **kwargs)
        result = wrapper
        result.__doc__ = fun.__doc__
        result.__name__ = fun.__name__
        result.__module__ = fun.__module__
        return result
    return inner
