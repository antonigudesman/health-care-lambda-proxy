from datetime import datetime

import boto3
import json
import os
import requests
from jose import jwt, jwk
from jose.utils import base64url_decode
import datetime
import uuid
from jwt_utils import get_jwks, verify_jwt
from medicaid_detail_utils import MedicaidDetail, convert_to_medicaid_detail, convert_to_medicaid_details_list, \
    create_uuid, FileInfo
from response_helpers import response_headers, missing_file_contents, \
    missing_file_name, expired_id_token, invalid_token, forbidden_action, options_response, \
    InvalidTokenError, ExpiredTokenError

BUCKET_NAME = os.environ.get('USER_FILES_BUCKET')
IS_TEST = os.environ.get('IS_TEST', True)
s3 = boto3.resource('s3')

"""
Request body should be like the following
{
    "action": "update-details",
    "key_to_update": "favorite_drink",
    "value_to_update": "{"value": "lemonade"}"
}
"""

# boto3 is the AWS SDK library for Python.
# The "resources" interface allow for a higher-level abstraction than the low-level client interface.
# More details here: http://boto3.readthedocs.io/en/latest/guide/resources.html
UPDATE_DETAILS = 'update-details'
GET_DETAILS = 'get-details'
GET_FILE = 'get-file'
UPLOAD_FILE = 'upload-file'
DELETE_FILE = 'delete-file'

endpoint_url = 'http://localhost:8000' if IS_TEST else None
dynamodb = boto3.resource('dynamodb', region_name='us-east-1', endpoint_url=endpoint_url)

table = dynamodb.Table(os.environ.get('TABLE', 'medicaid-details'))


def is_supported_action(action):
    return action in [GET_DETAILS, UPDATE_DETAILS, GET_FILE, UPLOAD_FILE, DELETE_FILE]


def get_claims(event_body):
    jwks = get_jwks()
    id_token = event_body['id_token']
    if not verify_jwt(id_token, jwks):
        raise InvalidTokenError

    claims = jwt.get_unverified_claims(id_token)
    if datetime.now().timestamp() > claims['exp']:
        raise ExpiredTokenError

    return claims


def handler(event, context):
    try:
        print(str(event))

        if event['httpMethod'] == 'OPTIONS':
            return options_response

        #   ------------------  validations  ---------------------------------------------

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

        #  ----------- end of validation - let's actually do something now   ----------------

        user_email = claims["cognito:username"]
        route_based_on_action(action, event_body, user_email)
        medicaid_details = get_details(user_email)

    except Exception as err:
        print(str(err))
        return {
            "statusCode": 500,
            "headers": response_headers,
            "body": json.dumps({"seems_successful": False})
        }

    return {
        "statusCode": 200,
        "headers": response_headers,
        "body": json.dumps({"success": True, "medicaid_details": medicaid_details})
    }


def route_based_on_action(action, event_body, user_email):
    if action == GET_DETAILS:
        ...

    elif action == UPDATE_DETAILS:
        update_details(user_email, event_body)

    elif action == GET_FILE:
        ...

    elif action == UPLOAD_FILE:
        return upload_file(user_email, event_body)

    elif action == DELETE_FILE:
        ...


def is_list_type(key_to_update):
    array_types = [
        'contacts', 'previous_addresses', 'documents'
    ]

    return key_to_update in array_types


def get_db_value(email, key_to_update):
    return get_details(email)['Item'].get(key_to_update, None)


def update_details(email, event_body):
    print(str(event_body))
    key_to_update = event_body['key_to_update']
    value_to_update = event_body['value_to_update']

    # if array -> map to proper medicaid details preserving or creating created date and uuid of what's already in db
    # else -> update db while keeping or creating created date and uuid

    val_from_db = get_db_value(email, key_to_update)
    value_to_update_medicaid_detail_format = None

    if is_list_type(key_to_update):
        value_to_update_medicaid_detail_format = convert_to_medicaid_details_list(key_to_update, value_to_update,
                                                                                  val_from_db)
    else:
        value_to_update_medicaid_detail_format = convert_to_medicaid_detail(key_to_update, value_to_update, val_from_db)

    # The BatchWriteItem API allows us to write multiple items to a table in one request.
    resp = table.update_item(
        Key={'email': email, 'application_name': 'my_application'},
        ExpressionAttributeNames={
            "#the_key": key_to_update
        },
        # Expression attribute values specify placeholders for attribute values to use in your update expressions.
        ExpressionAttributeValues={
            ":val_to_update": value_to_update_medicaid_detail_format,
        },
        # UpdateExpression declares the updates we want to perform on our item.
        # For more details on update expressions, see https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.UpdateExpressions.html
        UpdateExpression="SET #the_key = :val_to_update"
    )
    return resp

def add_document(email, event_body):
    print(str(event_body))
    key_to_update = 'documents'
    all_documents = event_body['value_to_update']

    # The BatchWriteItem API allows us to write multiple items to a table in one request.
    resp = table.update_item(
        Key={'email': email, 'application_name': 'my_application'},
        ExpressionAttributeNames={
            "#the_key": key_to_update
        },
        # Expression attribute values specify placeholders for attribute values to use in your update expressions.
        ExpressionAttributeValues={
            ":val_to_update": all_documents
        },
        # UpdateExpression declares the updates we want to perform on our item.
        # For more details on update expressions, see https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.UpdateExpressions.html
        UpdateExpression="SET #the_key = :val_to_update"
    )
    return resp

def get_details(email):
    medicaid_details = table.get_item(
        Key={
            'email': email, 'application_name': 'my_application'
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

    new_uuid = create_uuid()

    file_name = event_body['file_name']
    file_contents = event_body['file_contents']
    document_type = event_body['document_type']
    associated_medicaid_detail_uuid = event_body['associated_medicaid_detail_uuid']

    if not file_name:
        return missing_file_name
    if not file_contents:
        return missing_file_contents

    full_file_name = f'{user_email}/{file_name}'
    bucket_location = s3.Object(BUCKET_NAME,
                                full_file_name
                                #metadata={'uuid': new_uuid}
                                ).put(Body=file_contents)
    # s3.Object(bucket_name, "binyomin/test/tx").put(Body="this is just a test.  Please remain calm.")

    incoming_file_info = {
        'associated_medicaid_detail_uuid': associated_medicaid_detail_uuid,
        'document_type': document_type,
        'document_name': file_name,
        's3_location': bucket_location
    }

    val_from_db = get_db_value(user_email, 'documents')

    file_info = FileInfo(s3_location=incoming_file_info['s3_location'],
                         document_name=incoming_file_info['document_name'],
                         document_type=incoming_file_info['document_type'],
                         associated_medicaid_detail_uuid=incoming_file_info['associated_medicaid_detail_uuid'],
                         the_uuid=new_uuid
                         )

    list_of_file_infos = val_from_db.copy() if val_from_db else []

    list_of_file_infos.append(file_info.__dict__)

    update_dynamo_event_body = {
        "action": "add_document",
        "value_to_update": list_of_file_infos
    }

    add_document(user_email, update_dynamo_event_body)

def delete_file(user_email, the_uuid):
    delete_document_info_from_database(user_email, the_uuid)
    #delete_file_from_bucket(user_email, the_uuid)

def delete_document_info_from_database(user_email, the_uuid):
    all_documents_in_database =  get_db_value(user_email, 'documents')
    doc_to_delete = next((x for x in all_documents_in_database if x.uuid == the_uuid), None)
    if doc_to_delete:
        adjusted_document_list = all_documents_in_database.remove(doc_to_delete)
        resp = table.update_item(
            Key={'email': user_email, 'application_name': 'my_application'},
            ExpressionAttributeNames={
                "#the_key": 'documents'
            },
            # Expression attribute values specify placeholders for attribute values to use in your update expressions.
            ExpressionAttributeValues={
                ":val_to_update": adjusted_document_list
            },
            # UpdateExpression declares the updates we want to perform on our item.
            # For more details on update expressions, see https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.UpdateExpressions.html
            UpdateExpression="SET #the_key = :val_to_update"
        )
        return resp

