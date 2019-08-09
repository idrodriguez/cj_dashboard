import atexit
import json
import time
import re

import pusher
import requests
from envparse import env
from flask import Flask, render_template
from flask_bootstrap import Bootstrap
from jira import JIRA

import numpy as np
import pandas as pd
import plotly
import plotly.graph_objs as go
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
bootstrap = Bootstrap(app)

# Pusher client
pusher_client = pusher.Pusher(
    app_id = env('PUSHER_APP_ID'),
    key = env('PUSHER_KEY'),
    secret = env('PUSHER_SECRET'),
    cluster = env('PUSHER_CLUSTER'),
    ssl = True
)

# Routing Definition
@app.route('/')
def index():
    return render_template('dashboard.html', techDebtIssues = get_sprint_with_tech_debt())

@app.route('/idle_pbi')
def idlepbi():
    return render_template('pbi_idling.html', idlePBI = get_pbi_idle_current_sprint())

# Functions
def get_http_jira_client():
    jira_URL = env('JIRA_SERVER')
    jira_username = env('JIRA_USERNAME')
    jira_password = env('JIRA_PASSWORD')
    return JIRA(server=jira_URL, basic_auth=(jira_username, jira_password))

def get_tech_debt_issues():
    # Connect to JIRA and fetch the Technical Debt Items
    jira_tech_debt_issues = jira_client.search_issues('Team in (CustomerJourney) AND labels in (TechImprovements)')
    
    # Create list of records
    tech_debt_issues = []
    for issue in jira_tech_debt_issues:
        # Dirty hack to get the sprint name
        custom_field = issue.fields.customfield_10005
        sprint_name = "Backlog"
        if custom_field is not None:
            sprint_name = re.findall(r"name=[^,]*", str(custom_field[0]))[0][5:]
        
        tech_debt_issues.append([issue.key, sprint_name])

    return tech_debt_issues

def get_pbi_inprogress_current_sprint():
    jira_pbi_current_sprint = jira_client.search_issues('Team in (CustomerJourney) AND Sprint in openSprints() AND issuetype in (Story, Task, Bug) AND status = Implementing')
    jira_pbi_current_sprint_list = []

    for issue in jira_pbi_current_sprint:
        jira_pbi_current_sprint_list.append([issue.key, issue.fields.summary])

    return jira_pbi_current_sprint

def get_pbi_idle_current_sprint():
    jira_pbi_current_sprint = get_pbi_inprogress_current_sprint()
    pbi_idle = []
    for issue in jira_pbi_current_sprint:
        issues = jira_client.search_issues('parent = ' + issue.key + ' and status = Implementing')
        if issues.total == 0:
            pbi_idle.append({'key': issue.key, 'summary':  issue.fields.summary})
    return pbi_idle

def get_sprint_with_tech_debt():
    # Fetch the data from JIRA
    sprints = get_sprints_from_board(env('JIRA_BOARD'), "CustomerJourney")
    tech_debt_issues = get_tech_debt_issues()

    # Create data frames for sprint and technical debts
    df_tech_deb_issues = pd.DataFrame(tech_debt_issues, columns = ['Key', 'Sprint'])
    df_sprints = pd.DataFrame(sprints, columns = ['Sprint'])

    # Merge sprints with technical debts issues
    df_tech_deb_sprints = pd.merge(df_tech_deb_issues, df_sprints, on='Sprint', how='outer')

    # Group by Sprint and count the number of issues per sprint.
    df_tech_deb_sprints_group = df_tech_deb_sprints.groupby('Sprint').count()
    df_tech_deb_sprints_group = df_tech_deb_sprints_group.add_suffix('_Count').reset_index()

    # Create chart data
    data = [
        go.Bar(
                x=df_tech_deb_sprints_group['Sprint'],
                y=df_tech_deb_sprints_group['Key_Count']
            )
    ]

    graphJSON = json.dumps(data, cls=plotly.utils.PlotlyJSONEncoder)
    return graphJSON

def get_sprints_from_board(id, filter=None):
    # Fetch sprints from JIRA
    jira_sprints = jira_client.sprints(id)
    
    # Iterate per jira sprints and filter the list
    sprints = []
    for sprint in jira_sprints:
        if filter is not None:
            if filter in sprint.name:
                sprints.append(sprint.name)
        else:
            sprints.append(sprint.name)

    return sprints

def pushDataToChannel():
    # Trigger data
    pusher_client.trigger("customer_journey_dashboard", "tech_debt", get_sprint_with_tech_debt())

jira_client = get_http_jira_client()

if __name__ == '__main__':
    app.run(host='0.0.0.0')
