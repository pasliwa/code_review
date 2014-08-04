#!/usr/bin/python26

import logging
import getpass
from os.path import expanduser

activate_this = expanduser("~") + '/virtualenv/code_review/bin/activate_this.py'

execfile(activate_this, dict(__file__=activate_this))

from flup.server.fcgi import WSGIServer
from app import app
from app import logs

if __name__ == '__main__':
    logging.getLogger().addHandler(logs.get_file_handler("code_review.log"))
    logging.getLogger().addHandler(logs.get_mail_handler())
    username = getpass.getuser()
    WSGIServer(app, bindAddress='/tmp/' + username + '.sock').run()


