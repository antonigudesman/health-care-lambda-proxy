import os
import base64
import datetime

import boto3
import stripe

from typing import Dict
from mangum import Mangum
from fastapi import APIRouter, FastAPI
from boto3.dynamodb.conditions import Key
from fastapi.middleware.cors import CORSMiddleware

from config import API_V1_STR, PROJECT_NAME
from auth import get_email
from medicaid_detail_utils import *
from response_helpers import (
    response_headers, missing_file_contents, missing_file_name,
    invalid_token, forbidden_action, options_response, missing_files
)


app = FastAPI(title=PROJECT_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()

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


@router.post('/get-applications')
def get_applications(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token

    response = table.query(
        KeyConditionExpression=Key('email').eq(user_email)
    )

    return response['Items']


@router.post('/get-details')
def _get_details(body: Dict):
    user_email = get_email(body)
    if not user_email:
        return invalid_token
    application_uuid = body['application_uuid']

    resp = get_details(user_email, application_uuid)

    return resp


@router.post('/update-user-info')
def update_user_info(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token
    application_uuid = event_body['application_uuid']

    key_to_update = event_body['key_to_update']
    value_to_update = event_body['value_to_update']

    val_from_db = get_db_value(user_email, key_to_update, application_uuid)

    now = datetime.datetime.now().isoformat()
    user_info = UserInfo(updated_date=now, value=value_to_update)

    if val_from_db and 'created_date' in val_from_db:
        user_info.created_date = val_from_db['created_date']
    else:
        user_info.created_date = now

    resp = update_dynamodb(user_email, application_uuid, key_to_update, user_info.__dict__)

    return resp


@router.post('/update-details')
def update_details(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token
    application_uuid = event_body['application_uuid']
    key_to_update = event_body['key_to_update']
    value_to_update = event_body['value_to_update']

    val_from_db = get_db_value(user_email, key_to_update, application_uuid)
    value_to_update_medicaid_detail_format = None

    if is_list_type(key_to_update):
        value_to_update_medicaid_detail_format = convert_to_medicaid_details_list(key_to_update, value_to_update, val_from_db)
    else:
        value_to_update_medicaid_detail_format = convert_to_medicaid_detail(key_to_update, value_to_update, val_from_db)

    resp = update_dynamodb(user_email, application_uuid, key_to_update, value_to_update_medicaid_detail_format)

    return resp


@router.post('/upload-file')
def upload_file(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token
    application_uuid = event_body['application_uuid']
    associated_medicaid_detail_uuid = event_body['associated_medicaid_detail_uuid']
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

    resp = update_dynamodb(user_email, application_uuid, 'documents', documents)

    return resp


@router.post('/delete-file')
def delete_file(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token
    application_uuid = event_body['application_uuid']
    delete_document_info_from_database(user_email, event_body, application_uuid)


app.include_router(router, prefix=API_V1_STR)
handler = Mangum(app)
