# Database settings
DB_USER = "root"
DB_PWD = "secret"
SQLALCHEMY_DATABASE_URI = "mysql://root:secret@135.39.68.11/review"


# Flask settings
PROPAGATE_EXCEPTIONS = True
LISTEN_HOST = "0.0.0.0"
ENABLE_THREADS = False


# Code Collaborator settings
CCOLLAB_PATH = "/home/jenkins/ccollab-client"
CC_BIN = CCOLLAB_PATH + "/ccollab"
CC_REVIEW_URL="http://rd-w2k8.us.int.genesyslab.com:9090/go?page=ReviewDisplay&reviewid={reviewId}"


# Jenkins settings
JENKINS_URL = "http://pl-byd-srv01.emea.int.genesyslab.com:18080"
REVIEW_JOB_NAME = "iwd_8.5.000-REVIEW"



# Mercurial settings
REPO_PATH = "/home/jenkins/code_review/repo"
PRODUCT_BRANCHES = ("default", "master", "iwd-8.1.000", "iwd-8.1.001", "iwd-8.1.101-branch", "iwd-8.0.001", "iwd-8.0.002", "iwd-8.0.003")
IGNORED_BRANCHES = ("test", "qatest/datamart", "iwd_history_nosql")
