# Database settings
DB_USER = "root"
DB_PWD = "secret"
SQLALCHEMY_DATABASE_URI = "mysql://review:ChangeMe@pl-byd-srv01.emea.int.genesyslab.com/review"


# Flask settings
PROPAGATE_EXCEPTIONS = True     # change to False to get email notifications upon app errors
LISTEN_HOST = "0.0.0.0"
ENABLE_THREADS = True
SECRET_KEY = "ChangeMeLater"
PER_PAGE = 1


# Code Collaborator settings
CCOLLAB_PATH = "/home/jenkins/ccollab-client"
CC_BIN = CCOLLAB_PATH + "/ccollab"
CC_REVIEW_URL="http://rd-w2k8.us.int.genesyslab.com:9090/go?page=ReviewDisplay&reviewid={reviewId}"


# Jenkins settings
JENKINS_URL = "http://pl-byd-srv01.emea.int.genesyslab.com:18080"
REVIEW_JOB_NAME = "iwd_8.5.000-REVIEW"



# Mercurial settings
REPO_PATH = "/home/jenkins/code_review/repo"
PRODUCT_BRANCHES = ("iwd-8.5.000", "master", "iwd-8.1.000", "iwd-8.1.001", "iwd-8.1.101", "iwd-8.0.001", "iwd-8.0.002", "iwd-8.0.003")
IGNORED_BRANCHES = ("test", "qatest/datamart", "iwd_history_nosql")


# Flask-Security
SECURITY_PASSWORD_HASH = "sha512_crypt"
SECURITY_PASSWORD_SALT = "changeme"
SECURITY_EMAIL_SENDER = "Code Review <jenkins@pl-byd-srv01.emea.int.genesyslab.com>"
CSRF_ENABLED = False

SECURITY_FORGOT_PASSWORD_TEMPLATE = "security/forgot_password.html"
SECURITY_LOGIN_USER_TEMPLATE = "security/login_user.html"
SECURITY_REGISTER_USER_TEMPLATE = "security/register_user.html"
SECURITY_RESET_PASSWORD_TEMPLATE = "security/reset_password.html"
SECURITY_SEND_CONFIRMATION_TEMPLATE = "security/send_confirmation.html"
SECURITY_SEND_LOGIN_TEMPLATE = "security/send_login.html"

SECURITY_CONFIRMABLE = False
SECURITY_REGISTERABLE = True
SECURITY_RECOVERABLE = True
SECURITY_CHANGEABLE = True

