import requests
from atlassian import Jira
import re
from datetime import datetime
import asyncio

socradar_company_id = ''
socradar_api_key = ''
socradar_api_version = 'v4'
socradar_api_url = 'https://platform.socradar.com/api/company/'

request_type_field_id = 'customfield_'
request_type = ''
alarm_response_field_id = 'customfield_'
alarm_default_mitigation_plan_field_id = 'customfield_'
alarm_main_type_field_id = 'customfield_'
alarm_sub_type_field_id = 'customfield_'
project_key = 'soc'
reporter_account_id = ''

jira = Jira(
    url='https://instance.atlassian.net',
    username='',
    password='', # token
    cloud=True
)

def add_newline_before_number(text):
    result = re.sub(r'(\d+)', r'.\n\1', text)
    result = re.sub(r'^\.', '', result)
    return result

def check_existence(id):
    jql_request = f'project = {project_key} and summary ~ "{id}"'
    return jira.jql(jql_request).get('total')

async def create_issue():
    count = 1
    while True:
        print(f"Creating issues from page: {count}.")
        response = requests.get(f"{socradar_api_url}{socradar_company_id}/incidents/{socradar_api_version}?key={socradar_api_key}&is_resolved=0&is_false_positive=0&limit=100&page={count}")
        if response.status_code == 200:
            if len(response.json().get('data', [])) == 0:
                break
            data = response.json()
            for value in data.get('data', []):
                alarm_assignee = value.get('alarm_assignees', [])
                first_assignee = alarm_assignee[0] if alarm_assignee else "jsapalo@ictsi.com"
                alarm_summary = value.get('alarm_type_details').get('alarm_generic_title')
                alarm_id = value.get('alarm_id')
                alarm_main_type = value.get('alarm_type_details').get('alarm_main_type')
                alarm_sub_type = value.get('alarm_type_details').get('alarm_sub_type')
                alarm_text = value.get('alarm_text')
                parsed_text = f'{alarm_text[:32000]} ... (exceeds the character limit)' if len(alarm_text) > 32000 else alarm_text
                alarm_risk_level = value.get('alarm_risk_level')
                alarm_response = value.get('alarm_response')
                alarm_default_mitigation_plan = value.get('alarm_type_details').get('alarm_default_mitigation_plan')
                soc_issue = {
                    'project': {'key': {project_key}},
                    'summary': f"[{str(alarm_id)}] {alarm_summary}",
                    'description': parsed_text
                    + "\n\n"
                    + "Direct Link: "
                    + f"https://platform.socradar.com/app/company/{socradar_company_id}/alarm-management?tab=approved&alarmId={alarm_id}",
                    'issuetype': {'name': 'Incident'},
                    request_type_field_id: request_type,
                    'assignee': {
                        'accountId': jira.user_find_by_user_string(
                            query=first_assignee,
                            start=0,
                            limit=1,
                            include_inactive_users=False,
                        )[0].get('accountId')
                    },
                    alarm_response_field_id: add_newline_before_number(
                        alarm_response
                    ),
                    alarm_default_mitigation_plan_field_id: add_newline_before_number(
                        alarm_default_mitigation_plan
                    ),
                    'reporter': {
                        'accountId': {reporter_account_id}
                    },
                    'priority': {'name': str(alarm_risk_level).title()},
                    alarm_main_type_field_id: alarm_main_type,
                    alarm_sub_type_field_id: alarm_sub_type,
                }
                if check_existence(alarm_id) == 0:
                    try:
                        jira.issue_create(soc_issue)
                    except requests.exceptions.HTTPError as err:
                        if "cannot be assigned issues" in str(err):
                            soc_issue = {
                                'project': {'key': {project_key}},
                                'summary': f"[{str(alarm_id)}] {alarm_summary}",
                                'description': parsed_text
                                + "\n\n"
                                + "Direct Link: "
                                + f"https://platform.socradar.com/app/company/{socradar_company_id}/alarm-management?tab=approved&alarmId={alarm_id}",
                                'issuetype': {'name': 'Incident'},
                                request_type_field_id: request_type,
                                'assignee': {
                                    'accountId': jira.user_find_by_user_string(
                                        query=first_assignee,
                                        start=0,
                                        limit=1,
                                        include_inactive_users=False,
                                    )[0].get('accountId')
                                },
                                alarm_response_field_id: add_newline_before_number(
                                    alarm_response
                                ),
                                alarm_default_mitigation_plan_field_id: add_newline_before_number(
                                    alarm_default_mitigation_plan
                                ),
                                'reporter': {
                                    'accountId': {reporter_account_id}
                                },
                                'priority': {'name': str(alarm_risk_level).title()},
                                alarm_main_type_field_id: alarm_main_type,
                                alarm_sub_type_field_id: alarm_sub_type,
                            }
                            jira.issue_create(soc_issue)
                        else:
                            print(f"{err} at alarm id {str(alarm_id)}")
            count += 1
        else:
            print(f"Failed to retrieve data. Status code: {response.status_code}")

async def update_tickets(query, change_status):
    jql_request = query
    pattern = r'\[(.*?)\]'
    for issue in jira.jql(jql_request)['issues']:
        comments = jira.issue_get_comments(issue.get('key'))
        comment_text = "".join(
            f"""{comment.get('author').get('emailAddress')} commented at {datetime.strptime(comment.get('created'), "%Y-%m-%dT%H:%M:%S.%f%z")}: {comment.get('body')}. """
            for comment in comments.get('comments')
        )
        summary = issue.get('fields').get('summary')
        status = str(issue.get('fields').get('status').get('name')).upper()
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
        update_tickets(f"project = {project_key} and status = investigating", "1"),
        update_tickets(f"project = {project_key} and status = pending_info", "4"),
        update_tickets(f"project = {project_key} and status = legal_review", "5"),
        update_tickets(f"project = {project_key} and status = vendor_assessment", "6"),
        update_tickets(f"project = {project_key} and status = false_positive", "9"),
        update_tickets(f"project = {project_key} and status = duplicate", "10"),
        update_tickets(f"project = {project_key} and status = processed_internally", "11"),
        update_tickets(f"project = {project_key} and status = not_applicable", "13"),
        update_tickets(f"project = {project_key} and status = mitigated", "12"),
        update_tickets(f"project = {project_key} and status = resolved", "2"),
        update_tickets(f"project = {project_key} and status = open", "0")
    )

if __name__=="__main__":
    asyncio.run(main())
