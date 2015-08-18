from __future__ import absolute_import

from jira import JIRA
import re
import logging
from app.crypto import decryption

logger = logging.getLogger(__name__)

def token_search(commit):
    """ Search for tokens (IWD-XXXX, EVO-XXXX, IAP-XXXX) in commit """
    IWD = re.findall(r'[iI][wW][dD]-[0-9]{1,}', commit)
    EVO = re.findall(r'[eE][vV][oO]-[0-9]{1,}', commit)
    IAP = re.findall(r'[iI][aA][pP]-[0-9]{1,}', commit)
    return IWD + EVO + IAP
    
def comment_added(sha1, comments):
    """ Search for sha1 in comments """
    for comment in comments:
        if (sha1 in comment) and ('Code delivered by' in comment) and ('Branch: ' in comment):
            return True
    return False


def jira_comment(jira, issue_num, author, date, project, branch,
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
    
    jira = JIRA({'server': 'https://jira.genesys.com'}, basic_auth=(user.jira_login, decryption(user.jira_password)))
    
    for token in token_search(changeset.title):
        jira_comment(jira, token, changeset.owner, changeset.created_date, 'IWD', 
                        changeset.review.target, changeset.sha1, changeset.review_id, changeset.title)

def integrate_all_old(jira_login, enc_jira_password):
    """ Add comment to all relevant historical JIRA tickets """
    
    jira = JIRA({'server': 'https://jira.genesys.com'}, basic_auth=(jira_login, decryption(enc_jira_password)))
    
    for changeset in Changeset.query.filter(Changeset.Review.status == "MERGED").order_by(Changeset.created_date.asc()):
        for token in token_search(changeset.title):
            issue = jira.issue(token)
            if not comment_added(changeset.sha1, issue.fields.comment.comments):
                jira_comment(jira, token, changeset.owner, changeset.created_date, 'IWD', 
                                changeset.review.target, changeset.sha1, changeset.review_id, changeset.title)

            
