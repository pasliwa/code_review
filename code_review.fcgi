#!/usr/bin/python26

import getpass
from os.path import expanduser

activate_this = expanduser("~") + '/virtualenv/code_review/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))

from flup.server.fcgi import WSGIServer
from app import app

if __name__ == '__main__':
    username = getpass.getuser()
    WSGIServer(app, bindAddress='/tmp/' + username + '.sock').run()


