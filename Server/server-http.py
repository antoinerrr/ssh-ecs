#!/usr/bin/env python3

from flask import Flask
from flask import jsonify
from flask import make_response
from flask import request
from flask_httpauth import HTTPTokenAuth
from dateutil.tz import tzlocal
from tinydb import TinyDB, Query
import json
import boto3
import botocore
import datetime
import signal
import sys
import requests
import requests_cache
import serverSettings
import hvac
import uuid

db = TinyDB('db.json')

app = Flask(__name__)
auth = HTTPTokenAuth(scheme='Bearer')

if serverSettings.CACHE_ENABLE:
    requests_cache.install_cache(cache_name='github_cache', backend='sqlite', expire_after=180)


@auth.verify_token
def verify_token(token):
    headers = {'Authorization': 'token ' + token}
    login = requests.get('https://api.github.com/user', headers=headers)
    if "message" not in login.json():
        username = login.json()["login"]
        id = login.json()["id"]
        headers = {'Authorization': 'token ' + serverSettings.GITHUB_ADMIN_TOKEN}
        githubOrg = requests.get('https://api.github.com/orgs/' + serverSettings.GITHUB_ORG + '/members/' + username, headers=headers)
        if githubOrg.status_code == 204:
            return({"username": username, "id": id})


def verify_access(app, cluster, username):
    allowed_groups = serverSettings.MAP_GROUP[app][cluster]
    headers = {'Authorization': 'token ' + serverSettings.GITHUB_ADMIN_TOKEN}
    for allowed_group in allowed_groups:
        githubOrg = requests.get('https://api.github.com/orgs/' + serverSettings.GITHUB_ORG + '/teams/' + allowed_group + '/memberships/' + username, headers=headers)
        if githubOrg.status_code == 200:
            return True
    return False


def signal_handler(sig, frame):
    sys.exit(0)


def log_action(message):
    if serverSettings.LOG_DATADOG:
        headers = {'Content-type': 'application/json'}
        myobj = {"service": "ssh-tool", "message": message, "ddsource": "ssh-tool-server", "hostname": "ssh-bastion"}
        requests.post(serverSettings.DATADOG_URL, json=myobj, headers=headers)
    else:
        print(message)


def assumed_role_session(role_arn: str, base_session: botocore.session.Session = None):
    base_session = base_session or boto3.session.Session()._session
    fetcher = botocore.credentials.AssumeRoleCredentialFetcher(
        client_creator=base_session.create_client,
        source_credentials=base_session.get_credentials(),
        role_arn=role_arn,
        extra_args={}
    )
    creds = botocore.credentials.DeferredRefreshableCredentials(
        method='assume-role',
        refresh_using=fetcher.fetch_credentials,
        time_fetcher=lambda: datetime.datetime.now(tzlocal())
    )
    botocore_session = botocore.session.Session()
    botocore_session._credentials = creds
    return boto3.Session(botocore_session=botocore_session)


def createBotoClient(app, ecs=True, ec2=False):
    if app not in serverSettings.MAP_GROUP:
        return(False)
    if serverSettings.MAP_GROUP[app]["aws"] != "root":
        session = assumed_role_session(serverSettings.MAP_GROUP[app]["aws"])
        client_ecs = session.client('ecs', region_name=serverSettings.MAP_GROUP[app]["region"])
        if ec2:
            client_ec2 = session.client('ec2', region_name=serverSettings.MAP_GROUP[app]["region"])
    else:
        client_ecs = boto3.client('ecs', region_name=serverSettings.MAP_GROUP[app]["region"])
        if ec2:
            client_ec2 = boto3.client('ec2', region_name="eu-west-1")
    if ec2:
        return(client_ecs, client_ec2)
    else:
        return(client_ecs)


#
#    SEND HEALTH
#
#
@app.route('/health')
def sendHealth():
    return("ok")


#
#    SEND MENU
#
#
@app.route('/menu')
@auth.login_required
def sendMenu():
    resp = make_response(jsonify(serverSettings.MENU))
    resp.headers['Ssh-Tool-User'] = auth.current_user()["username"]
    resp.headers['Ssh-Tool-Version'] = serverSettings.VERSION
    return(resp)


#
#    SEND SERVICE
#
#
@app.route('/services/<app>/<cluster>')
@auth.login_required
def sendServices(app, cluster):
    client = createBotoClient(app)
    if not client:
        return(jsonify({"error": "UNSUPORTED"}))
    response = client.list_services(
                    cluster=cluster
                )
    return(jsonify(response["serviceArns"]))


#
#    SEND TASKS
#
#
@app.route('/tasks/<app>/<cluster>', methods=['POST'])
@auth.login_required
def sendTasks(app, cluster):
    if "service" in request.json:
        service = request.json["service"]
        client = createBotoClient(app)
        if not client:
            return(jsonify({"error": "UNSUPORTED"}))
        response = client.list_tasks(
            cluster=cluster,
            serviceName=service.split("/")[1],
            desiredStatus='RUNNING'
        )
        if len(response["taskArns"]) == 0:
            return(jsonify({"error": "UNSUPORTED"}))
        else:
            return(json.dumps(response["taskArns"]))
    else:
        return(jsonify({"error": "missig arg"}))


#
#    SEND CONTAINERS
#
#
@app.route('/containers/<app>/<cluster>', methods=['POST'])
@auth.login_required
def sendContainers(app, cluster):
    if "task" in request.json:
        task = request.json["task"]
        client = createBotoClient(app)
        if not client:
            return(jsonify({"error": "UNSUPORTED"}))
        response = client.describe_tasks(
                    cluster=cluster,
                    tasks=[
                        task.split("/")[-1],
                    ],
                )
        containers = list()
        for container in response["tasks"][0]["containers"]:
            containers.append(container["containerArn"] + " - " + container["name"])
        return(jsonify(containers))
    else:
        return(jsonify({"error": "missig arg"}))


#
# GET CONTAINER DETAILS
#
#
def getConnectDetail(app, cluster, task, container):
    client, client_ec2 = createBotoClient(app, ec2=True)
    if not client:
        return(jsonify({"error": "UNSUPORTED"}))
    response = client.describe_tasks(
                cluster=cluster,
                tasks=[
                    task.split("/")[1],
                ])
    runtimeId = ""
    for cont in response["tasks"][0]["containers"]:
        if container.split(" ")[0] == cont["containerArn"]:
            runtimeId = cont["runtimeId"]
    response = client.describe_container_instances(
                cluster=cluster,
                containerInstances=[
                    response["tasks"][0]["containerInstanceArn"],
                ])
    ec2_id = response["containerInstances"][0]["ec2InstanceId"]
    response = client_ec2.describe_instances(
                InstanceIds=[
                    ec2_id,
                ]
            )
    log_action("User " + auth.current_user()["username"] + " requested access to " + cluster)
    vault_client = hvac.Client(
        url=serverSettings.VAULT_ADDR,
        token=serverSettings.VAULT_TOKEN, verify=False)
    otp = vault_client.write(
        serverSettings.VAULT_SECRET, ip=response["Reservations"][0]["Instances"][0]["NetworkInterfaces"][0]["PrivateIpAddress"])["data"]["key"]
    return(jsonify({"ip": response["Reservations"][0]["Instances"][0]["NetworkInterfaces"][0]["PrivateIpAddress"], "container": runtimeId, "OTP": otp}))


#
#    SEND CONNECTION DETAILS
#
#
@app.route('/connect/<app>/<cluster>', methods=['POST'])
@auth.login_required
def sendConnect(app, cluster):
    if "task" in request.json:
        task = request.json["task"]
        if "container" in request.json:
            container = request.json["container"]
        else:
            return(jsonify({"error": "missig arg"}))
        # Check if user is allowed
        if not verify_access(app, cluster, auth.current_user()["username"]):
            return(jsonify({"error": "Not_Allowed"}))
        return(getConnectDetail(app, cluster, task, container))
    else:
        return(jsonify({"error": "missig arg"}))


#
#
# ASK TEMP ACCESS
#
@app.route('/asktemp/<app>/<cluster>', methods=['POST'])
@auth.login_required
def askTemp(app, cluster):
    if "task" in request.json:
        task = request.json["task"]
        if "container" in request.json:
            container = request.json["container"]
        else:
            return(jsonify({"error": "missig arg"}))
        user = auth.current_user()["username"]
        uuidRequester = str(uuid.uuid4())
        uuidValidator = str(uuid.uuid4())
        webhook_url = serverSettings.SLACK_URL
        slack_data = {'username': 'SSH-ECS', 'text': "User: `" + user + "` wants to access to *" + app + "* - *" + cluster + "*. To accept this request, please run the following command as an admin :julsign: : \n `sshecs --allow " + uuidValidator + "`"}
        requests.post(
            webhook_url, data=json.dumps(slack_data),
            headers={'Content-Type': 'application/json'}
            )
        db.insert({'name': user, 'app': app, 'cluster': cluster, 'task': task, 'container': container, 'uuidValidator': uuidValidator, 'uuidRequester': uuidRequester, 'valid': False})
        return(jsonify({"token": uuidRequester}))
    else:
        return(jsonify({"error": "missig arg"}))


#
#
# check TEMP ACCESS
#
@app.route('/checktemp/<id>')
@auth.login_required
def checkTemp(id):
    db_request = Query()
    db_result = db.search(db_request.uuidRequester == id)
    if len(db_result) == 0:
        return(jsonify({"status": "invalid"}))
    else:
        if db_result[0]["valid"]:
            return(getConnectDetail(db_result[0]["app"], db_result[0]["cluster"], db_result[0]["task"], db_result[0]["container"]))
        else:
            return(jsonify({"status": "waiting"}))


#
#
# Validate TEMP ACCESS
#
@app.route('/validatetemp/<id>')
@auth.login_required
def validateTemp(id):
    if not verify_access("allow_admin", "admin", auth.current_user()["username"]):
        return(jsonify({"error": "Not_Allowed"}))
    db_request = Query()
    db_result = db.search(db_request.uuidValidator == id)
    db.upsert({'name': db_result[0]["name"], 'app': db_result[0]["app"], 'cluster': db_result[0]["cluster"], 'task': db_result[0]["task"], 'container': db_result[0]["container"], 'uuidValidator': db_result[0]["uuidValidator"], 'uuidRequester':db_result[0]["uuidRequester"], 'valid': True}, db_request.uuidValidator == id)
    return(jsonify({"status": "ok"}))


def start():
    app.run(host="0.0.0.0", debug=True)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    print("[Info] server is starting...")
    start()
