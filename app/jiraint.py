from jira import JIRA
import re

def token_search(commit):
	IWD = re.findall(r'[iI][wW][dD]-[0-9]{1,}', commit)
	EVO = re.findall(r'[eE][vV][oO]-[0-9]{1,}', commit)
	IAP = re.findall(r'[iI][aA][pP]-[0-9]{1,}', commit)
	return IWD + EVO + IAP

def jira_comment(login, password, options, issue_num, author, date,
					project, branch, link_hgweb, link_detektyw, commit_msg):
	""" Add comment to relevant JIRA ticket """
	jira = JIRA(options, basic_auth=(login, password))
	issue = jira.issue(issue_num)
	
	comment = 'Code delivered by *{author}* on {date}.\n'.format(author=author, date=date)
	comment += 'Branch: {project}/{branch}\n'.format(project=project, branch=branch)
	comment += 'Commit: [{link_hgweb}]\n'.format(link_hgweb=link_hgweb)
	comment += 'Inspection: {link_detektyw}\n'.format(link_detektyw=link_detektyw)
	comment += 'Commit message:\n\n{commit_msg}\n\n'.format(commit_msg=commit_msg)
	
	jira.add_comment(issue, comment)


com = "Test for integration IAP-48 and IAP-49"
options = {
    'server': 'https://jira.genesys.com'
}

