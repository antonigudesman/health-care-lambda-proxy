import os

import boto3
import stripe


BUCKET_NAME = os.environ.get('USER_FILES_BUCKET')

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table(os.environ.get('TABLE', 'medicaid-details'))
s3 = boto3.resource('s3')


def update_dynamodb(email, application_uuid, key, val):
    resp = table.update_item(
        Key={'email': email, 'application_uuid': application_uuid},
        ExpressionAttributeNames={ "#the_key": key },
        ExpressionAttributeValues={ ":val_to_update": val },
        UpdateExpression="SET #the_key = :val_to_update"
    )

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


def get_db_value(email, key_to_update, application_uuid):
    return get_details(email, application_uuid)['Item'].get(key_to_update, None)


def is_list_type(key_to_update):
    array_types = [
        'contacts',
        'previous_addresses',
        'documents',
        'general.vehicles',
        'general-vehicles',
        'employment_income.income_employment_details',
        'employment_income-income_employment_details',
        'insurance_policies.insurance_policies_details',
        'insurance_policies-insurance_policies_details',
        'general.properties',
        'general-properties',
        'general.property_proceeds',
        'general-property_proceeds',
        'financials.account_details',
        'financials-account_details',
        'financials.life_insurance_stocks_details',
        'financials-life_insurance_stocks_details'
    ]

    return key_to_update in array_types


def delete_document_info_from_database(user_email, event_body, application_uuid):
    documents = get_db_value(user_email, 'documents', application_uuid)

    file_name = event_body['file_name']
    document_type = event_body['document_type']

    clean_documents = [doc for doc in documents if doc['document_name'] != file_name or doc['document_type'] != document_type]

    resp = update_dynamodb(user_email, application_uuid, 'documents', clean_documents)

    return resp


def handle_checkout_session_succeeded(checkout_session):
    #application_uuid = checkout_session.client_reference_id
    payment_intent_id = checkout_session.payment_intent
    payment_intent = stripe.PaymentIntent.retrieve(
        payment_intent_id
    )

    print(payment_intent)
