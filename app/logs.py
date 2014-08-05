import os
import logging
import logging.handlers
from logging.handlers import SMTPHandler, RotatingFileHandler

from app import app

EMAIL_LOG_TEMPLATE = '''
Message type:       %(levelname)s
Thread:             %(threadName)s
Location:           %(pathname)s:%(lineno)d
Module:             %(module)s
Function:           %(funcName)s
Time:               %(asctime)s

Message:

%(message)s
'''

FILE_LOG_TEMPLATE = "%(asctime)s <%(threadName)s> %(levelname)s [%(name)s:%(lineno)d] %(message)s"

CONSOLE_LOG_TEMPLATE = "%(levelname)s <%(threadName)s> [%(name)s:%(lineno)d] %(message)s"

def get_mail_handler():
    mail_handler = SMTPHandler('127.0.0.1',
                               app.config["SECURITY_EMAIL_SENDER"],
                               app.config["ADMIN_EMAILS"],
                               'Code Review application failed')
    mail_handler.setLevel(logging.WARNING)
    mail_handler.setFormatter(logging.Formatter(EMAIL_LOG_TEMPLATE))
    return mail_handler

def get_file_handler(filename):
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    file_handler = RotatingFileHandler(os.path.join(log_dir, filename),
                                       maxBytes=104857600, backupCount=30)
    file_handler.setFormatter(logging.Formatter(FILE_LOG_TEMPLATE))
    file_handler.setLevel(logging.DEBUG)
    return file_handler

def get_console_handler():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(FILE_LOG_TEMPLATE))
    handler.setLevel(logging.DEBUG)
    return handler


# don't change this!
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger("app.mercurial").setLevel(logging.INFO)
