#!/usr/bin/python26

import logging

activate_this = '/home/ci_test/virtualenv/code_review/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))

from flup.server.fcgi import WSGIServer
from app import app
from app import logs

if __name__ == '__main__':
    logging.getLogger().addHandler(logs.get_file_handler("code_review.log"))
    logging.getLogger().addHandler(logs.get_mail_handler())
    WSGIServer(app, bindAddress='/tmp/ci_test.sock').run()


