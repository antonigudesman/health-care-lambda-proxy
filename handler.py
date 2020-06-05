import os
import json
import base64
import logging

from datetime import datetime

import boto3
from jose import jwt, jwk
from boto3.dynamodb.conditions import Key
from jwt_utils import get_jwks, verify_jwt

from medicaid_detail_utils import (
    MedicaidDetail, convert_to_medicaid_detail, convert_to_medicaid_details_list,
    create_uuid, FileInfo, UserInfo
)
from response_helpers import (
    response_headers, missing_file_contents, missing_file_name, expired_id_token,
    invalid_token, forbidden_action, options_response, InvalidTokenError,
    ExpiredTokenError, missing_files
)

BUCKET_NAME = os.environ.get('USER_FILES_BUCKET')
IS_TEST = os.environ.get('IS_TEST', True)
DEV_JWKS_URL = 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_c1urqyqMM/.well-known/jwks.json'
JWKS_URL = os.environ.get('JWKS_URL', DEV_JWKS_URL)
if IS_TEST == 'False':
    IS_TEST = False
s3 = boto3.resource('s3')

"""
Request body should be like the following
{
    "action": "update-details",
    "key_to_update": "favorite_drink",
    "value_to_update": "lemonade"
}
"""

# boto3 is the AWS SDK library for Python.
# The "resources" interface allow for a higher-level abstraction than the low-level client interface.
# More details here: http://boto3.readthedocs.io/en/latest/guide/resources.html
DELETE_FILE = 'delete-file'
GET_APPLICATIONS = 'get-applications'
GET_DETAILS = 'get-details'
GET_FILE = 'get-file'
UPDATE_DETAILS = 'update-details'
UPDATE_RECORD = 'update-user-info'
UPLOAD_FILE = 'upload-file'

endpoint_url = 'http://localhost:8000' if IS_TEST else None
dynamodb = boto3.resource('dynamodb', region_name='us-east-1', endpoint_url=endpoint_url)

table = dynamodb.Table(os.environ.get('TABLE', 'medicaid-details'))


def is_supported_action(action):
    return action in [GET_DETAILS, UPDATE_DETAILS, GET_FILE, UPLOAD_FILE, DELETE_FILE, GET_APPLICATIONS, UPDATE_RECORD]


def get_claims(event_body):
    jwks = get_jwks(JWKS_URL)
    id_token = event_body['id_token']
    if not verify_jwt(id_token, jwks):
        raise InvalidTokenError

    claims = jwt.get_unverified_claims(id_token)
    if datetime.now().timestamp() > claims['exp']:
        raise ExpiredTokenError

    return claims


def update_dynamodb(email, application_uuid, key, val):
    resp = table.update_item(
        Key={'email': email, 'application_uuid': application_uuid},
        ExpressionAttributeNames={ "#the_key": key },
        ExpressionAttributeValues={ ":val_to_update": val },
        UpdateExpression="SET #the_key = :val_to_update"
    )

    return resp


def handler(event, context):
    try:
        print(str(event))

        if event['httpMethod'] == 'OPTIONS':
            return options_response

        event_body = json.loads(event['body'])
        action = event_body['action']

        if not is_supported_action(action):
            return forbidden_action
        try:
            claims = get_claims(event_body)
        except InvalidTokenError:
            return invalid_token
        except ExpiredTokenError:
            return expired_id_token

        user_email = claims["cognito:username"]
        res_body = route_based_on_action(action, event_body, user_email)

    except Exception as err:
        logger  = logging.getLogger()
        logger.exception(str(err))
        return {
            "statusCode": 500,
            "headers": response_headers,
            "body": json.dumps({"seems_successful": False})
        }

    return {
        "statusCode": 200,
        "headers": response_headers,
        "body": json.dumps(res_body)
    }


def get_applications(user_email):
    response = table.query(
        KeyConditionExpression=Key('email').eq(user_email)
    )
    return response['Items']


def route_based_on_action(action, event_body, user_email):
    application_uuid = event_body['application_uuid']

    if action == GET_DETAILS:
        return get_details(user_email, application_uuid)

    elif action == GET_APPLICATIONS:
        return get_applications(user_email)

    elif action == UPDATE_DETAILS:
        update_details(user_email, event_body)
        return get_details(user_email, application_uuid)

    elif action == GET_FILE:
        ...

    elif action == UPDATE_RECORD:
        update_user_info(user_email, event_body)
        return get_details(user_email, application_uuid)

    elif action == UPLOAD_FILE:
        upload_file(user_email, event_body)
        return get_details(user_email, application_uuid)

    elif action == DELETE_FILE:
        delete_file(user_email, event_body, application_uuid)
        return get_details(user_email, application_uuid)


def is_list_type(key_to_update):
    array_types = [
        'contacts', 'previous_addresses', 'documents'
    ]

    return key_to_update in array_types


def get_db_value(email, key_to_update, application_uuid):
    return get_details(email, application_uuid)['Item'].get(key_to_update, None)


def update_user_info(email, event_body):
    print(str(event_body))
    key_to_update = event_body['key_to_update']
    value_to_update = event_body['value_to_update']
    application_uuid = event_body['application_uuid']

    val_from_db = get_db_value(email, key_to_update, application_uuid)

    now = datetime.now().isoformat()
    user_info = UserInfo(updated_date=now, value=value_to_update)

    if val_from_db and 'created_date' in val_from_db:
        user_info.created_date = val_from_db['created_date']
    else:
        user_info.created_date = now

    resp = update_dynamodb(email, application_uuid, key_to_update, user_info.__dict__)

    return resp


def update_details(email, event_body):
    print(str(event_body))
    key_to_update = event_body['key_to_update']
    value_to_update = event_body['value_to_update']
    application_uuid = event_body['application_uuid']

    # if array -> map to proper medicaid details preserving or creating created date and uuid of what's already in db
    # else -> update db while keeping or creating created date and uuid

    val_from_db = get_db_value(email, key_to_update, application_uuid)
    value_to_update_medicaid_detail_format = None

    if is_list_type(key_to_update):
        value_to_update_medicaid_detail_format = convert_to_medicaid_details_list(key_to_update, value_to_update, val_from_db)
    else:
        value_to_update_medicaid_detail_format = convert_to_medicaid_detail(key_to_update, value_to_update, val_from_db)

    resp = update_dynamodb(email, application_uuid, key_to_update, value_to_update_medicaid_detail_format)

    return resp


def get_details(email, application_uuid):
    medicaid_details = table.get_item(
        Key={
            'email': email, 'application_uuid': application_uuid
        },
        ConsistentRead=True,
        ReturnConsumedCapacity='NONE',
    )

    return medicaid_details


def upload_file(user_email, event_body):
    """
    need to have multiple documents per medicaid detail
    documents column
    [
        {
            uuid: 'adslkajlkjlk'  (this will be used by front end for deleting)
            associated_medicaid_detail_uuid: 'lkjljklkj' (John Doe's uuid)  (This will be useful by front end for retrieving)
            document_type: 'POA'
            created_date: '2020....'
            document_name: 'bobPOA2019.jpg'
            s3_location: 'sdsdfsdfsdf....'
        }
    ]

    :param user_email:
    :param event_body:
    :return:
    """
    associated_medicaid_detail_uuid = event_body['associated_medicaid_detail_uuid']
    application_uuid = event_body['application_uuid']
    document_type = event_body['document_type']
    files = event_body['files']

    if not files:
        return missing_files

    documents = get_db_value(user_email, 'documents', application_uuid) or []

    for file in files:
        file_name = file['file_name']
        file_contents = file['file_contents']

        if not file_name:
            return missing_file_name

        if not file_contents or file_contents == 'data:':
            return missing_file_contents

        # remove base64 prefix for correct upload to s3.
        idx = file_contents.find(';base64,')
        file_contents = file_contents[idx+8:]
        full_file_name = f'{user_email}/{application_uuid}/{document_type}/{file_name}'

        s3.Object(BUCKET_NAME, full_file_name).put(Body=base64.b64decode(file_contents))
        s3_location = f'https://{BUCKET_NAME}.s3.amazonaws.com/{full_file_name}'

        file_info = FileInfo(s3_location=s3_location,
                             document_name=file_name,
                             document_type=document_type,
                             associated_medicaid_detail_uuid=associated_medicaid_detail_uuid,
                             the_uuid=create_uuid()
                             )

        documents.append(file_info.__dict__)

    resp = update_dynamodb(email, application_uuid, 'documents', documents)

    return resp


def delete_file(user_email, event_body, application_uuid):
    delete_document_info_from_database(user_email, event_body, application_uuid)
    # delete_file_from_bucket(user_email, the_uuid)


def delete_document_info_from_database(user_email, event_body, application_uuid):
    documents = get_db_value(user_email, 'documents', application_uuid)

    file_name = event_body['file_name']
    document_type = event_body['document_type']

    clean_documents = [doc for doc in documents if doc['document_name'] != file_name or doc['document_type'] != document_type]

    resp = update_dynamodb(email, application_uuid, 'documents', clean_documents)

    return resp
