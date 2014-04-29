import os
import logging
import logging.handlers
from logging.handlers import SMTPHandler, RotatingFileHandler

from app import app
from app.utils import get_admin_emails

ADMINS = get_admin_emails()

mail_handler = SMTPHandler('127.0.0.1',
                           'jenkins@pl-byd-srv01.emea.int.genesyslab.com',
                           ADMINS, 'Code Review application failed')
mail_handler.setLevel(logging.ERROR)
mail_handler.setFormatter(logging.Formatter('''
Message type:       %(levelname)s
Location:           %(pathname)s:%(lineno)d
Module:             %(module)s
Function:           %(funcName)s
Time:               %(asctime)s

Message:

%(message)s
'''))

here = os.path.dirname(__file__)
file_handler = RotatingFileHandler(os.path.join(here, "../logs/code_review.log"), maxBytes=104857600, backupCount=30)
log_format = "%(asctime)s %(levelname)s [%(name)s:%(lineno)d] %(message)s"
file_handler.setFormatter(logging.Formatter(log_format))
file_handler.setLevel(logging.DEBUG)

# don't change this!
app.logger.setLevel(logging.DEBUG)
app.logger.addHandler(file_handler)
app.logger.addHandler(mail_handler)
