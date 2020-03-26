import boto3
import json

# boto3 is the AWS SDK library for Python.
# The "resources" interface allow for a higher-level abstraction than the low-level client interface.
# More details here: http://boto3.readthedocs.io/en/latest/guide/resources.html
UPDATE_DETAILS = 'update-details'
CREATE_USER = 'create-user'
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('MedicaidDetails-sps-qa-1')


def handler(event, context):
    try:
        event_body = json.loads(event['body'])
        print(json.dumps(event_body))
        action = event_body['action']
        if action not in [CREATE_USER, UPDATE_DETAILS]:
            return

        if action == CREATE_USER:
            ...
            # create_user(event_body)
        elif action == UPDATE_DETAILS:
            update_details(event_body)
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
        "body": json.dumps({"seems_successful": True})
    }


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

# def create_user(event_body):
#     email = event_body['email']
#     # The BatchWriteItem API allows us to write multiple items to a table in one request.
#     try:

#         with table.batch_writer() as batch:
#             batch.put_item(Item={"email": email})

#     except Exception as err:
#         print(err)
