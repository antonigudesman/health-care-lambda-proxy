from datetime import datetime

import boto3
import json
import os
import requests
from jose import jwt, jwk
from jose.utils import base64url_decode

"""
Request body should be like the following
{
    "action": "update-details",
    "id_token": "ljlklkjlkjlklklkjlkjlkjlkj",
    "key_to_update": "favorite_drink",
    "value_to_update": "not that one"
}
"""

# boto3 is the AWS SDK library for Python.
# The "resources" interface allow for a higher-level abstraction than the low-level client interface.
# More details here: http://boto3.readthedocs.io/en/latest/guide/resources.html
UPDATE_DETAILS = 'update-details'
GET_DETAILS = 'get-details'
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table(os.environ.get('TABLE', 'MedicaidDetails-sps-qa-1'))


def handler(event, context):
    try:
        event_body = json.loads(event['body'])
        print(json.dumps(event_body))
        action = event_body['action']
        if action not in [GET_DETAILS, UPDATE_DETAILS]:
            return {
                "statusCode": 403,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "hmm we dont let this"})
            }

        jwks = get_jwks()
        id_token = event_body['id_token']
        if not verify_jwt(id_token, jwks):
            return {
                "statusCode": 403,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "invalid id token"})
            }

        claims = jwt.get_unverified_claims(id_token)
        print('claims are')
        print(json.dumps(claims))
        if datetime.now().timestamp() > claims['exp']:
            return {
                "statusCode": 403,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "expired id token"})
            }

        user_email = claims["cognito:username"]

        if action == GET_DETAILS:
            ...

        elif action == UPDATE_DETAILS:
            update_details(user_email, event_body)

        medicaid_details = get_details(user_email)
    except Exception as err:
        print(str(err))
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"seems_successful": False})
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"success": True, "medicaid_details": medicaid_details})
    }


def update_details(email, event_body):
    print(str(event_body))
    key_to_update = event_body['key_to_update']
    value_to_update = event_body['value_to_update']

    # The BatchWriteItem API allows us to write multiple items to a table in one request.
    resp = table.update_item(
        Key={"email": email},
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


def get_details(email):
    medicaid_details = table.get_item(
        Key={
            'email': email
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
