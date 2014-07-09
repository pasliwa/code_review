#!/usr/bin/python26

activate_this = '/home/ci_test/virtualenv/code_review/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))


import time
import logging
import threading


class Anacron(threading.Thread):
    def __init__(self, interval, function, title):
        self.title = title
        self.interval = interval
        self.function = function

    def run(self):
        while True:
            try:
                self.function()
            except:
                logging.exception("Exception in " + self.title)
            delay = time.time() % self.interval
            time.sleep(delay)


# Update mercurial

# Update jenkins

# Schedule jenkins

# Schedule CodeCollaborator

if __name__ == '__main__':
    pass