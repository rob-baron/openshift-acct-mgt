import kubernetes
import pprint
import logging
import requests
import json
import re
import os
from flask import Flask, redirect, url_for, request, Response
# from flask_restful import reqparse

import sys

from openshift_rolebindings import *
from openshift_project import *
from openshift_identity import *
from openshift_user import *
from openshift_resource_quota import *

application = Flask(__name__)

if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    application.logger.handlers = gunicorn_logger.handlers
    application.logger.setLevel(gunicorn_logger.level)


def get_user_token():
    with open('/var/run/secrets/kubernetes.io/serviceaccount/token', 'r') as file:
        token = file.read()
        return token
    return ""


def get_token_and_url():
    token = get_user_token()
    openshift_url = os.environ["openshift_url"]
    return (token, openshift_url)


@application.route("/users/<user_name>/projects/<project_name>/roles/<role>", methods=['GET'])
def get_moc_rolebindings(project_name, user_name, role):
    # role can be one of Admin, Member, Reader
    (token, openshift_url) = get_token_and_url()
    if(exists_user_rolebinding(token, openshift_url, user_name, project_name, role)):
        return Response(
            response=json.dumps(
                {"msg": "user role exists ("+project_name + "," + user_name + "," + role + ")"}),
            status=200,
            mimetype='application/json'
        )
    return Response(
        response=json.dumps(
            {"msg": "user role does not exists ("+project_name + "," + user_name + "," + role + ")"}),
        status=404,
        mimetype='application/json'
    )


@application.route("/users/<user_name>/projects/<project_name>/roles/<role>", methods=['PUT'])
def create_moc_rolebindings(project_name, user_name, role):
    # role can be one of Admin, Member, Reader
    (token, openshift_url) = get_token_and_url()
    r = update_user_role_project(
        token, openshift_url, project_name, user_name, role, 'add')
    return r


@application.route("/users/<user_name>/projects/<project_name>/roles/<role>", methods=['DELETE'])
def delete_moc_rolebindings(project_name, user_name, role):
    # role can be one of Admin, Member, Reader
    (token, openshift_url) = get_token_and_url()
    r = update_user_role_project(
        token, openshift_url, project_name, user_name, role, 'del')
    return r


@application.route("/projects/<project_uuid>", methods=['GET'])
@application.route("/projects/<project_uuid>/owner/<user_name>", methods=['GET'])
def get_moc_project(project_uuid, user_name=None):
    (token, openshift_url) = get_token_and_url()
    if(exists_openshift_project(token, openshift_url, project_uuid)):
        return Response(
            response=json.dumps(
                {"msg": "project exists (" + project_uuid + ")"}),
            status=200,
            mimetype='application/json'
        )
    return Response(
        response=json.dumps(
            {"msg": "project does not exist (" + project_uuid + ")"}),
        status=400,
        mimetype='application/json'
    )


@application.route("/projects/<project_uuid>", methods=['PUT'])
@application.route("/projects/<project_uuid>/owner/<user_name>", methods=['PUT'])
def create_moc_project(project_uuid, user_name=None):
    (token, openshift_url) = get_token_and_url()
    # first check the project_name is a valid openshift project name
    suggested_project_name = cnvt_project_name(project_uuid)
    if(project_uuid != suggested_project_name):
        # future work, handel colisons by suggesting a different valid
        # project name
        return Response(
            response=json.dumps(
                {"msg": "ERROR: project name must match regex '[a-z0-9]([-a-z0-9]*[a-z0-9])?'", "suggested name": suggested_project_name}),
            status=400,
            mimetype='application/json'
        )
    if(not exists_openshift_project(token, openshift_url, project_uuid)):
        project_name = project_uuid
        if("Content-Length" in request.headers):
            req_json = request.get_json(force=True)
            if("displayName" in req_json):
                project_name = req_json["displayName"]
            application.logger.debug("create project json: "+project_name)
        else:
            application.logger.debug("create project json: None")

        r = create_openshift_project(
            token, openshift_url, project_uuid, project_name, user_name)
        if(r.status_code == 200 or r.status_code == 201):
            return Response(
                response=json.dumps(
                    {"msg": "project created (" + project_uuid + ")"}),
                status=200,
                mimetype='application/json'
            )
        return Response(
            response=json.dumps(
                {"msg": "project unabled to be created (" + project_uuid + ")"}),
            status=400,
            mimetype='application/json'
        )
    return Response(
        response=json.dumps(
            {"msg": "project currently exist (" + project_uuid + ")"}),
        status=400,
        mimetype='application/json'
    )


@application.route("/projects/<project_uuid>", methods=['DELETE'])
@application.route("/projects/<project_uuid>/owner/<user_name>", methods=['DELETE'])
def delete_moc_project(project_uuid, user_name=None):
    (token, openshift_url) = get_token_and_url()
    if(exists_openshift_project(token, openshift_url, project_uuid)):
        r = delete_openshift_project(
            token, openshift_url, project_uuid, user_name)
        if(r.status_code == 200 or r.status_code == 201):
            return Response(
                response=json.dumps(
                    {"msg": "project deleted (" + project_uuid + ")"}),
                status=200,
                mimetype='application/json'
            )
        return Response(
            response=json.dumps(
                {"msg": "project unabled to be deleted (" + project_uuid + ")"}),
            status=400,
            mimetype='application/json'
        )
    return Response(
        response=json.dumps(
            {"msg": "unable to delete, project does not exist(" + project_uuid + ")"}),
        status=400,
        mimetype='application/json'
    )


@application.route("/users/<user_name>", methods=['GET'])
def get_moc_user(user_name, full_name=None, id_provider="sso_auth", id_user=None):
    (token, openshift_url) = get_token_and_url()
    r = None
    if(exists_openshift_user(token, openshift_url, user_name)):
        return Response(
            response=json.dumps({"msg": "user (" + user_name + ") exists"}),
            status=200,
            mimetype='application/json'
        )
    return Response(
        response=json.dumps(
            {"msg": "user (" + user_name + ") does not exist"}),
        status=400,
        mimetype='application/json'
    )


@application.route("/users/<user_name>", methods=['PUT'])
def create_moc_user(user_name, full_name=None, id_provider="sso_auth", id_user=None):
    token, openshift_url = get_token_and_url()

    # A user in OpenShift is composed of 3 parts: user, identity, and identitymapping.
    user_exists = exists_openshift_user(token, openshift_url, user_name)
    if not user_exists:
        r = create_openshift_user(token, openshift_url, user_name, full_name)

        if r.status_code not in [200, 201]:
            return Response(
                response=json.dumps(
                    {"msg": "unable to create openshift user (" + user_name + ") 1"}),
                status=400,
                mimetype='application/json'
            )

    if id_user is None:
        id_user = user_name

    identity_exists = exists_openshift_identity(
        token, openshift_url, id_provider, id_user)
    if not identity_exists:
        r = create_openshift_identity(
            token, openshift_url, id_provider, id_user)

        if r.status_code not in [200, 201]:
            return Response(
                response=json.dumps(
                    {"msg": "unable to create openshift identity (" + id_provider + ")"}),
                status=400,
                mimetype='application/json'
            )

    mapping_exists = exists_openshift_useridentitymapping(
        token, openshift_url, user_name, id_provider, id_user)
    if not mapping_exists:
        r = create_openshift_useridentitymapping(
            token, openshift_url, user_name, id_provider, id_user)

        if r.status_code not in [200, 201]:
            return Response(
                response=json.dumps(
                    {"msg": "unable to create openshift user identity mapping (" + user_name + ")"}),
                status=400,
                mimetype='application/json'
            )

    if user_exists and identity_exists and mapping_exists:
        return Response(
            response=json.dumps(
                {"msg": "user currently exists (" + user_name + ")"}),
            status=200,
            mimetype='application/json'
        )
    return Response(
        response=json.dumps({"msg": "user created (" + user_name + ")"}),
        status=200,
        mimetype='application/json'
    )


@application.route("/users/<user_name>", methods=['DELETE'])
def delete_moc_user(user_name, full_name=None, id_provider="sso_auth", id_user=None):
    token, openshift_url = get_token_and_url()

    user_exists = exists_openshift_user(token, openshift_url, user_name)
    if user_exists:
        r = delete_openshift_user(token, openshift_url, user_name, full_name)
        if r.status_code not in [200, 201]:
            return Response(
                response=json.dumps(
                    {"msg": "unable to delete User (" + user_name + ") 1"}),
                status=400,
                mimetype='application/json'
            )

    if id_user is None:
        id_user = user_name

    identity_exists = exists_openshift_identity(
        token, openshift_url, id_provider, id_user)
    if identity_exists:
        r = delete_openshift_identity(
            token, openshift_url, id_provider, id_user)

        if r.status_code not in [200, 201]:
            return Response(
                response=json.dumps(
                    {"msg": "unable to delete identity (" + id_provider + ")"}),
                status=400,
                mimetype='application/json'
            )

    if not user_exists and not identity_exists:
        return Response(
            response=json.dumps(
                {"msg": "user does not currently exist (" + user_name + ")"}),
            status=200,
            mimetype='application/json'
        )
    return Response(
        response=json.dumps({"msg": "user deleted (" + user_name + ")"}),
        status=200,
        mimetype='application/json'
    )


@application.route("/quota/<project_name>/resourcequota/<resource_name>", methods=['GET'])
def get_resource_quotas(project_name, resource_name):
    (token, openshift_url) = get_token_and_url()
    r = None
    if(exists_openshift_resource_quota(token, openshift_url, project_name, resource_name)):
        r = get_openshift_resource_quota(
            token, openshift_url, project_name, resource_name)
        return Response(
            response=json.dumps(
                {"msg": " Quota exists for (" + resource_name + ")", "specifications": r}),
            status=200,
            mimetype='application/json'
        )
    return Response(
        response=json.dumps({"msg": "No Quotas with name  (" +
                             resource_name + ") in project (" + project_name + ") "}),
        status=400,
        mimetype='application/json'
    )


@application.route("/quotas/<project_name>", methods=['GET'])
def getAll_resource_quotas(project_name):
    (token, openshift_url) = get_token_and_url()
    r = None
    r = getAll_openshift_resource_quota(token, openshift_url, project_name)
    data = r.json()
    for element in data['items']:
        del element['status']
    if(r.status_code == 200 or r.status_code == 201):
        return Response(
            response=json.dumps(
                {"msg": " All Quotas that exists for project (" + project_name + ").", "get-quotas": data}),
            status=200,
            mimetype='application/json'
        )
    return Response(
        response=json.dumps(
            {"msg": "No Quotas in project (" + project_name + ") "}),
        status=400,
        mimetype='application/json'
    )


def perform_quota_operation(token, openshift_url, project_name, resource_name, pay_load):
    resp_msg = ""
    status_code = 200
    if(not exists_openshift_resource_quota(token, openshift_url, project_name, resource_name)):
        if(create_openshift_resource_quota(token, openshift_url, project_name, pay_load)):
            resp_msg = "Quota created Sucessfully for the project ({}) and the quota is ({})".format(
                project_name, pay_load["spec"])
        else:
            resp_msg = "Unable to create quota for the project({}) and the quota is ({})".format(
                project_name, pay_load["spec"])
    else:
        resp_msg = "Quota already exists with ({}) in project ({}) and the quota is ({})".format(
            resource_name, project_name, pay_load["spec"])
        status_code = 400
    return resp_msg, status_code


@application.route("/quota/<project_name>/<resource_name>", methods=['POST'])
def create_resource_quota(project_name, resource_name):
    (token, openshift_url) = get_token_and_url()
    r = None
    if(request.is_json):
        req = request.get_json()

        if "QuotaList" in req:
            quotaList = list(req["QuotaList"])
            req.pop("QuotaList", None)
            resp_msg=""

            for quota in quotaList:
                item_keys = []
                item_value = 0
                for key, value in quota.items():
                    item_keys = key.split(":")
                    item_value = value

                spec = {}
                spec[item_keys[1]] = {item_keys[2]: item_value}
                spec["scopes"] = [item_keys[0]]
                req["spec"] = spec
                resp_msg1, status_code = perform_quota_operation(token, openshift_url, project_name, resource_name, req)
                resp_msg = resp_msg + resp_msg1
        else:
            resp_msg, status_code = perform_quota_operation(
                token, openshift_url, project_name, resource_name, req)

        return Response(response=json.dumps({"msg": resp_msg}), status=status_code, mimetype='application/json')

    else:
        return Response(
            response=json.dumps({"Msg": "Input type should be JSON"}),
            status=400,
            mimetype='application/json'
        )


@application.route("/update-quota/<project_name>/resourcequota/<resource_name>", methods=['PATCH'])
def update_resource_quota(project_name, resource_name):
    (token, openshift_url) = get_token_and_url()
    if(request.is_json):
        object_def = request.get_json()
    change_requested = object_def['spec']['hard']
    if(exists_openshift_resource_quota(token, openshift_url, project_name, resource_name)):
        r = get_openshift_resource_quota(
            token, openshift_url, project_name, resource_name)

        def get_key(val):
            for key, value in change_requested.items():
                if val == value:
                    return key
            return "key doesn't exist"
        for a in change_requested:
            if(a in r):
                r[a] = change_requested[a]
            else:
                l = get_key(change_requested[a])
                r.update({l: change_requested[a]})

        object_def['spec']['hard'] = r

        r = update_openshift_resource_quota(
            token, openshift_url, project_name, object_def, resource_name)
        if(r.status_code == 200 or r.status_code == 201):
            return Response(
                response=json.dumps({"msg": "Quota updated with latest specifications ",
                                     "updated-specification": object_def['spec']['hard']}),
                status=200,
                mimetype='application/json'
            )
        else:
            return Response(
                response=json.dumps(
                    {"msg": "Unable to update resource quotas for project (" + resource_name + ") "}),
                status=400,
                mimetype='application/json'
            )
    else:
        return Response(
            response=json.dumps({"msg": " No such quotas exists with (" +
                                 resource_name + " ) in project  (" + project_name + ")"}),
            status=400,
            mimetype='application/json')


@application.route("/quota/<project_name>/resourcequota/<resource_name>", methods=['DELETE'])
def delete_resource_quota(project_name, resource_name):
    (token, openshift_url) = get_token_and_url()
    r = None
    if(exists_openshift_resource_quota(token, openshift_url, project_name, resource_name)):
        r = delete_openshift_resource_quota(
            token, openshift_url, project_name, resource_name)
        data = r.json()
        if(r.status_code == 200 or r.status_code == 201):
            return Response(
                response=json.dumps(
                    {"msg": "Quota Deleted Successfully", "Details": data['metadata']}),
                status=200,
                mimetype='application/json'
            )
        return Response(
            response=json.dumps(
                {"msg": "Unable to delete resource quotas are assosiated with (" + project_name + ") "}),
            status=400,
            mimetype='application/json'
        )
    else:
        return Response(
            response=json.dumps({"msg": "No such quotas exists with (" +
                                 resource_name + " ) in project  (" + project_name + ")"}),
            status=400,
            mimetype='application/json'
        )


if __name__ == "__main__":
    application.run()
