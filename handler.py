from datetime import datetime

import boto3
import json
import os
import requests
from jose import jwt, jwk
from jose.utils import base64url_decode
s3 = boto3.resource('s3')
bucket_name = os.environ.get('USER_FILES_BUCKET', 'turbocaid--user-files--sps-qa-1')



"""
Request body should be like the following
{
    "action": "update-details",
    "key_to_update": "favorite_drink",
    "value_to_update": "not that one"
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

IS_TEST = os.environ.get('IS_TEST', True)
endpoint_url = 'http://localhost:8000' if IS_TEST else None
dynamodb = boto3.resource('dynamodb', region_name='us-east-1', endpoint_url=endpoint_url)

table = dynamodb.Table(os.environ.get('TABLE', 'medicaid-details'))

response_headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,OPTIONS,POST"
}

responses = {
    "options_response": {
                "statusCode": 200,
                "headers": response_headers,
                "body": json.dumps({"message": "successful options response"})
            },
    "forbidden_action": {
                "statusCode": 403,
                "headers": response_headers,
                "body": json.dumps({"error": "hmm we dont let this"})
            },
    "invalid_token": {
                "statusCode": 403,
                "headers": response_headers,
                "body": json.dumps({"error": "invalid id token"})
            },
    "expired_id_token": {
                "statusCode": 403,
                "headers": response_headers,
                "body": json.dumps({"error": "expired id token"})
            },
    "missing_file_name": {
        "statusCode": 400,
        "headers": response_headers,
        "body": json.dumps({"error": "missing file name"})
    },
    "missing_file_contents": {
        "statusCode": 400,
        "headers": response_headers,
        "body": json.dumps({"error": "missing file contents"})
    }

}


def handler(event, context):
    try:
        print(str(event))

        #   ------------------  validations  ---------------------------------------------
        if event['httpMethod'] == 'OPTIONS':
            return responses['options_response']

        event_body = json.loads(event['body'])
        print(json.dumps(event_body))
        action = event_body['action']
        if action not in [GET_DETAILS, UPDATE_DETAILS, GET_FILE, UPLOAD_FILE, DELETE_FILE]:
            return responses['forbidden_action']

        jwks = get_jwks()
        id_token = event_body['id_token']
        if not verify_jwt(id_token, jwks):
            return responses['invalid_token']

        claims = jwt.get_unverified_claims(id_token)
        print('claims are')
        print(json.dumps(claims))
        if datetime.now().timestamp() > claims['exp']:
            return responses['expired_id_token']

        #  ----------- end of validation - let's actually do something now   ----------------

        user_email = claims["cognito:username"]

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


def update_details(email, event_body):
    print(str(event_body))
    key_to_update = event_body['key_to_update']
    value_to_update = event_body['value_to_update']

    # The BatchWriteItem API allows us to write multiple items to a table in one request.
    resp = table.update_item(
        Key={'email': email, 'application_name': 'my_application'},
        ExpressionAttributeNames={
            "#the_key": key_to_update
        },
        # Expression attribute values specify placeholders for attribute values to use in your update expressions.
        ExpressionAttributeValues={
            ":val_to_update": value_to_update,
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
        return responses['missing_file_name']
    if not file_contents:
        return responses['missing_file_contents']

    full_file_name = f'{user_email}/{file_name}'
    s3.Object(bucket_name, full_file_name).put(Body=file_contents)
    #s3.Object(bucket_name, "binyomin/test/tx").put(Body="this is just a test.  Please remain calm.")
