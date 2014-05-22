#!/usr/bin/python26

activate_this = '/home/ci_test/virtualenv/code_review/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))

from flup.server.fcgi import WSGIServer
from app import app

if __name__ == '__main__':
    WSGIServer(app, bindAddress='/tmp/ci_test.sock').run()


