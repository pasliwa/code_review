from __future__ import absolute_import

from jira import JIRA
import re
import datetime
import logging
from app.crypto import decryption

logger = logging.getLogger(__name__)

def token_search(commit):
    """ Search for tokens (IWD-XXXX, EVO-XXXX, IAP-XXXX) in commit """
    IWD = re.findall(r'[iI][wW][dD]-[0-9]{1,}', commit)
    EVO = re.findall(r'[eE][vV][oO]-[0-9]{1,}', commit)
    IAP = re.findall(r'[iI][aA][pP]-[0-9]{1,}', commit)
    return IWD + EVO + IAP

def jira_comment(issue_num, author, date, project, branch,
                                link_hgweb, link_detektyw, commit_msg):
    """ Add comment to single relevant JIRA ticket """
    
    issue = jira.issue(issue_num)
    
    comment = 'Code delivered by *{author}* on {date}.\n'.format(author=author, date=date)
    comment += 'Branch: {project}/{branch}\n'.format(project=project, branch=branch)
    comment += 'Commit: http://hg.genesyslab.com/hgweb.cgi/iwd8/rev/{link_hgweb}\n'.format(link_hgweb=link_hgweb)
    comment += 'Inspection: http://pl-byd-srv01.emea.int.genesyslab.com/ci/review/{link_detektyw}\n'.format(link_detektyw=link_detektyw)
    comment += 'Commit message:\n{noformat}'
    comment += '\n{commit_msg}\n'.format(commit_msg=commit_msg)
    comment += '{noformat}\n'
    
    jira.add_comment(issue, comment)
    logger.info('Added comment to {issue}'.format(issue=issue_num))

def jira_integrate(changeset, user):
    """ Add comment to all relevant JIRA tickets """
    
    now = datetime.datetime.now()
    current_date = "{day}/{month}/{year}".format(day=now.day, month=now.month, year=now.year)
    jira = JIRA({'server': 'https://jira.genesys.com'}, basic_auth=(user.jira_login, decryption(user.jira_password)))
    
    for token in token_search(changeset.title):
        jira_comment(token, changeset.owner, current_date, 'IWD', 
                    changeset.review.target,changeset.sha1, changeset.review_id, changeset.title)
