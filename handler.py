import boto3
import json
import os
"""
Request body should be like the following
{
    "action": "update-details",
    "email": "binyominco@gmail.com",
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
        new_user_request = event['request']
        if new_user_request:
            new_user_response = create_new_user(new_user_request)
            return new_user_response

        event_body = json.loads(event['body'])
        print(json.dumps(event_body))
        action = event_body['action']
        if action not in [GET_DETAILS, UPDATE_DETAILS]:
            return {
                "statusCode": 403,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "hmm we dont let this"})
            }

        if action == GET_DETAILS:
            ...

        elif action == UPDATE_DETAILS:
            update_details(event_body)

        medicaid_details = get_details(event_body)
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


def create_new_user(new_user_request):
    print(new_user_request)
    user_email = new_user_request['userAttributes']['email']
    response = table.put_item(
        Item={
            'email': user_email
        },
        ReturnValues='NONE'
    )
    return response
    """
    {'userAttributes': {'sub': 'eb1b4430-5b0e-44c9-ac42-36bca41935e5', 'cognito:user_status': 'CONFIRMED', 'email_verified': 'true', 'phone_number_verified': 'false', 'phone_number': '+7036092827', 'given_name': 'Sean', 'family_name': 'Cohen', 'email': 'binyominco@gmail.com'}}
    """


def update_details(event_body):
    print(str(event_body))
    email = event_body['email']
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


def get_details(event_body):
    medicaid_details = table.get_item(
        Key={
            'email': event_body['email']
        },
        ConsistentRead=True,
        ReturnConsumedCapacity='NONE',
    )

    return medicaid_details
