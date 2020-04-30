from datetime import datetime

import boto3
import json
import os
import requests
from jose import jwt, jwk
from jose.utils import base64url_decode
import datetime
import uuid
from response_helpers import response_headers, missing_file_contents,\
    missing_file_name, expired_id_token, invalid_token, forbidden_action, options_response,\
    InvalidTokenError, ExpiredTokenError

bucket_name = os.environ.get('USER_FILES_BUCKET', 'turbocaid--user-files--sps-qa-1')
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


class MedicaidDetail:
    def __init__(self,  value,  updated_date, the_uuid=None, created_date=None):
        self.uuid = the_uuid
        self.created_date = created_date
        self.updated_date = updated_date
        self.value = value


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
        'contacts', 'previous_addresses'
    ]

    return key_to_update in array_types


def convert_to_medicaid_details_list(key_to_update, value_to_update, val_from_db):
    dict_of_db_vals ={item['uuid']: item for item in val_from_db} if val_from_db else {}

    # dict_by_uuid = {}  # {'u8982-w98rw9r': {theitemfromdb}}
    # for medicaid_detail in db_list:
    #     dict_by_uuid[medicaid_detail['uuid']] = medicaid_detail

    medicaid_details_to_insert = []
    for detail_item_to_update in value_to_update:
        now = datetime.datetime.now().isoformat()

        medicaid_detail = MedicaidDetail(updated_date=now, value=detail_item_to_update['value'])

        if 'uuid' in detail_item_to_update:
            the_uuid = detail_item_to_update['uuid']
            try:
                db_item = dict_of_db_vals[uuid]
            except Exception as err:
                print(f'could not find corresponding item in db with uuid {the_uuid}')
            medicaid_detail.uuid = the_uuid
            medicaid_detail.created_date = db_item['created_date']
        else:
            medicaid_detail.uuid = uuid.uuid4().hex
            medicaid_detail.created_date = datetime.datetime.now().isoformat()
        
        medicaid_details_to_insert.append(medicaid_detail.__dict__)
        
        return medicaid_details_to_insert


def convert_to_medicaid_detail(key_to_update, value_to_update, val_from_db):
    now = datetime.datetime.now().isoformat()
    medicaid_detail = MedicaidDetail(updated_date=now, value=value_to_update['value'])
    if val_from_db:     
        medicaid_detail.uuid = val_from_db['uuid']
        medicaid_detail.created_date = val_from_db['created_date']
    else:
        medicaid_detail.uuid = uuid.uuid4().hex
        medicaid_detail.created_date = now
        
    return medicaid_detail.__dict__


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
        value_to_update_medicaid_detail_format = convert_to_medicaid_details_list(key_to_update, value_to_update, val_from_db)
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


def get_details(email):
    medicaid_details = table.get_item(
        Key={
            'email': email, 'application_name': 'my_application'
        },
        ConsistentRead=True,
        ReturnConsumedCapacity='NONE',
    )

    return medicaid_details


def get_jwks():
    return requests.get(
        f"https://cognito-idp.us-east-1.amazonaws.com/us-east-1_IiYvInxsJ/.well-known/jwks.json"
    ).json()


def get_hmac_key(token: str, jwks):
    kid = jwt.get_unverified_header(token).get("kid")
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key


def verify_jwt(token: str, jwks) -> bool:
    hmac_key = get_hmac_key(token, jwks)

    if not hmac_key:
        raise ValueError("No pubic key found!")

    hmac_key = jwk.construct(get_hmac_key(token, jwks))

    message, encoded_signature = token.rsplit(".", 1)

    decoded_signature = base64url_decode(encoded_signature.encode())

    return hmac_key.verify(message.encode(), decoded_signature)


def upload_file(user_email, event_body):
    file_name = event_body['fileName']
    file_contents = event_body['fileContents']
    if not file_name:
        return missing_file_name
    if not file_contents:
        return missing_file_contents

    full_file_name = f'{user_email}/{file_name}'
    s3.Object(bucket_name, full_file_name).put(Body=file_contents)
    #s3.Object(bucket_name, "binyomin/test/tx").put(Body="this is just a test.  Please remain calm.")
