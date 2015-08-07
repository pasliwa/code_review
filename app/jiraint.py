from jira import JIRA
import re
import datetime

def token_search(commit):
	""" Search for tokens (IWD-XXXX, EVO-XXXX, IAP-XXXX) in commit """
	IWD = re.findall(r'[iI][wW][dD]-[0-9]{1,}', commit)
	EVO = re.findall(r'[eE][vV][oO]-[0-9]{1,}', commit)
	IAP = re.findall(r'[iI][aA][pP]-[0-9]{1,}', commit)
	return IWD + EVO + IAP

def jira_comment(login, password, options, issue_num, author, date,
					project, branch, link_hgweb, link_detektyw, commit_msg):
	""" Add comment to single relevant JIRA ticket """
	jira = JIRA(options, basic_auth=(login, password))
	issue = jira.issue(issue_num)
	
	comment = 'Code delivered by *{author}* on {date}.\n'.format(author=author, date=date)
	comment += 'Branch: {project}/{branch}\n'.format(project=project, branch=branch)
	comment += 'Commit: http://hg.genesyslab.com/hgweb.cgi/iwd8/rev/{link_hgweb}\n'.format(link_hgweb=link_hgweb)
	comment += 'Inspection: http://pl-byd-srv01.emea.int.genesyslab.com/ci/review/{link_detektyw}\n'.format(link_detektyw=link_detektyw)
	comment += 'Commit message:\n{noformat}'
	comment += '\n{commit_msg}\n'.format(commit_msg=commit_msg)
	comment += '{noformat}\n'
	
	jira.add_comment(issue, comment)

def jira_integrate(cs_id, user):
	""" Add comment to all relevant JIRA tickets """
	changeset = Changeset.query.filter(Changeset.id == cs_id).first()
	now = datetime.datetime.now()
	for token in token_search(changeset.title):
		current_date = "{day}/{month}/{year}".format(day=now.day, month=now.month, year=now.year)
		jira_comment(user.jira_login, user.jira_password, {'server': 'https://jira.genesys.com'}, 
						token, changeset.owner, current_date, 'IWD', changeset.review.target,
						changeset.sha1, changeset.review_id, changeset.title)
