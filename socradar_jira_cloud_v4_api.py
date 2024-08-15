import requests
from atlassian import Jira
import re
import pprint
from datetime import datetime
import asyncio

socradar_company_id = ""
socradar_api_key = ""
socradar_api_version = "v4"
socradar_api_url = "https://platform.socradar.com/api/company/"

jira = Jira(
    url='https://.atlassian.net',
    username='',
    password='',
    cloud=True
)

def add_newline_before_number(text):
    result = re.sub(r'(\d+)', r'.\n\1', text)
    result = re.sub(r'^\.', '', result)
    return result

def check_existence(id):
    jql_request = f'project = soc and summary ~ "{id}"'
    total = jira.jql(jql_request).get('total')
    return total

async def create_issue():
    count = 1
    while True:
        print(f"Creating issues from page: {count}.")
        response = requests.get(f"{socradar_api_url}{socradar_company_id}/incidents/{socradar_api_version}?key={socradar_api_key}&is_resolved=0&is_false_positive=0&severities=HIGH&limit=100&page={count}")
        if response.status_code == 200:
            if len(response.json().get('data', [])) != 0:
                data = response.json()
                for value in data.get('data', []):
                    alarm_assignee = value.get('alarm_assignees', [])
                    first_assignee = alarm_assignee[0] if alarm_assignee else "email@atlassian.net"
                    alarm_summary = value.get('alarm_type_details').get('alarm_generic_title')
                    alarm_id = value.get('alarm_id')
                    alarm_main_type = value.get('alarm_type_details').get('alarm_main_type')
                    alarm_sub_type = value.get('alarm_type_details').get('alarm_sub_type')
                    alarm_text = value.get('alarm_text')
                    alarm_risk_level = value.get('alarm_risk_level')
                    alarm_response = value.get('alarm_response')
                    alarm_default_mitigation_plan = value.get('alarm_type_details').get('alarm_default_mitigation_plan')
                    alarm_content = value.get('content')
                    soc_issue = {
                    'project': {'key': 'SOC'},
                    'summary': "[" + str(alarm_id) + "] " +  alarm_summary,
                    'description': alarm_text + "\n\n" + pprint.pformat(alarm_content) + "\n\nDirect Link: " + f"{socradar_api_url}{socradar_company_id}/alarm-management?tab=approved&alarmId={alarm_id}",
                    'issuetype': {'name': 'Incident'},
                    'customfield_': '', # request type field
                    'assignee': {'accountId': jira.user_find_by_user_string(query=first_assignee, start=0, limit=1, include_inactive_users=False)[0].get('accountId')},
                    'customfield_': add_newline_before_number(alarm_response), # alarm response field
                    'customfield_': add_newline_before_number(alarm_default_mitigation_plan), # mitigation plan field
                    'reporter': {'accountId':''},
                    'priority': {'name':str(alarm_risk_level).title()},
                    'customfield_': alarm_main_type, # alarm main type field
                    'customfield_': alarm_sub_type # alarm sub type field
                    }
                    if check_existence(alarm_id) == 0:
                        try:
                            jira.issue_create(soc_issue)
                        except requests.exceptions.HTTPError as err:
                            if "cannot be assigned issues" in str(err):
                                soc_issue = {
                                'project': {'key': 'SOC'},
                                'summary': "[" + str(alarm_id) + "] " +  alarm_summary,
                                'description': alarm_text + "\n\n" + pprint.pformat(alarm_content) + "\n\nDirect Link: " + f"{socradar_api_url}{socradar_company_id}/alarm-management?tab=approved&alarmId={alarm_id}",
                                'issuetype': {'name': 'Incident'},
                                'customfield_': '', # request type field
                                'assignee': {'accountId': jira.user_find_by_user_string(query=first_assignee, start=0, limit=1, include_inactive_users=False)[0].get('accountId')},
                                'customfield_': add_newline_before_number(alarm_response), # alarm response field
                                'customfield_': add_newline_before_number(alarm_default_mitigation_plan), # mitigation plan field
                                'reporter': {'accountId':''},
                                'priority': {'name':str(alarm_risk_level).title()},
                                'customfield_': alarm_main_type, # alarm main type field
                                'customfield_': alarm_sub_type # alarm sub type field
                                }
                                jira.issue_create(soc_issue)
                            else:
                                print(err + " at alarm id " + str(alarm_id))
                count += 1
            else:
                break
        else:
            print(f"Failed to retrieve data. Status code: {response.status_code}")

async def update_tickets(query, change_status):
    jql_request = query
    for issue in jira.jql(jql_request)['issues']:
        comments = jira.issue_get_comments(issue.get('key'))
        comment_text = ""
        for comment in comments.get('comments'):
            comment_text += f"{comment.get('author').get('emailAddress')} commented at {datetime.strptime(comment.get('created'), "%Y-%m-%dT%H:%M:%S.%f%z")}: {comment.get('body')}. "
        summary = issue.get('fields').get('summary')
        status = str(issue.get('fields').get('status').get('name')).upper()
        pattern = r'\[(.*?)\]'
        alarm_ids = re.findall(pattern, summary)
        for alarm_id in alarm_ids:
            check_status = requests.get(f"{socradar_api_url}{socradar_company_id}/incidents/{socradar_api_version}?key={socradar_api_key}&alarm_ids={alarm_id}")
            if check_status.status_code == 200:
                for alarm_status in check_status.json().get('data'):
                    if status != alarm_status.get('status'):
                        headers = { "Content-Type": "application/json", "API-KEY": socradar_api_key }
                        payload = { "alarm_ids": alarm_id, "status": change_status, "comments": comment_text }
                        response = requests.post(f"{socradar_api_url}{socradar_company_id}/alarms/status/change", json = payload, headers = headers)
                        print(response.text)

async def main():
    await asyncio.gather(
        create_issue(),
        update_tickets("project = soc and status = investigating", "1"),
        update_tickets("project = soc and status = pending_info", "4"),
        update_tickets("project = soc and status = legal_review", "5"),
        update_tickets("project = soc and status = vendor_assessment", "6"),
        update_tickets("project = soc and status = false_positive", "9"),
        update_tickets("project = soc and status = duplicate", "10"),
        update_tickets("project = soc and status = processed_internally", "11"),
        update_tickets("project = soc and status = not_applicable", "13"),
        update_tickets("project = soc and status = mitigated", "12"),
        update_tickets("project = soc and status = resolved", "2"),
        update_tickets("project = soc and status = open", "0")
    )

if __name__=="__main__":
    asyncio.run(main())
