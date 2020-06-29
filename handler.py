import base64
import datetime

import stripe

from typing import Dict
from mangum import Mangum
from fastapi import APIRouter, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from boto3.dynamodb.conditions import Key

from config import API_V1_STR, PROJECT_NAME
from auth import get_email
from utils import *
from medicaid_detail_utils import *
from response_helpers import (
    response_headers, missing_file_contents, missing_file_name,
    invalid_token, forbidden_action, options_response, missing_files, 
    invalid_signature, unknown_event_type, invalid_request
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


try:
    kms = boto3.client('kms')
    stripe_api_key = kms.decrypt(CiphertextBlob=base64.b64decode(os.getenv('STRIPE_API_KEY')))['Plaintext'].decode()
except Exception as err:
    stripe_api_key = os.getenv('STRIPE_API_KEY')
stripe.api_key = stripe_api_key


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
    print ('Update dynamodb result:', resp)
    resp = get_details(user_email, application_uuid)

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
    print ('Update dynamodb result:', resp)
    resp = get_details(user_email, application_uuid)

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
    print ('Update dynamodb result:', resp)
    resp = get_details(user_email, application_uuid)

    return resp


@router.post('/delete-file')
def delete_file(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token
    application_uuid = event_body['application_uuid']
    delete_document_info_from_database(user_email, event_body, application_uuid)


@router.post('/create-payment-session')
def create_payment_session(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token
    application_uuid = event_body['application_uuid']
    react_app_url = os.getenv('REACT_APP_URL')
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price': event_body['price_id'],
            'quantity': 1,
        }],
        mode='payment',
        client_reference_id=application_uuid,
        success_url=f'{react_app_url}/payment/success?sessionId={CHECKOUT_SESSION_ID}',
        cancel_url=f'{react_app_url}/payment',
    )
    return session.id


@router.post('/completed-checkout-session')
def completed_checkout_session(request: Request):
    try:
        endpoint_secret = kms.decrypt(CiphertextBlob=base64.b64decode(os.getenv('WEBHOOK_SECRET')))['Plaintext'].decode()
    except Exception as e:
        endpoint_secret = os.getenv('WEBHOOK_SECRET')
    try:
        event_body = request.scope['aws.event']['body']
        stripe_signature = request.scope['aws.event']['headers']['Stripe-Signature']
    except KeyError:
        return invalid_request
    try:
        event = stripe.Webhook.construct_event(
            event_body, stripe_signature, endpoint_secret
        )
    except ValueError as e:
        return {
            "statusCode": 400,
            "headers": response_headers
        }
    except stripe.error.SignatureVerificationError:
        return invalid_signature

    if event.type == 'checkout.session.completed':
        try:
            checkout_session = event.data.object
            handle_checkout_session_succeeded(checkout_session)
        except Exception as e:
            print('Error handling successful checkout session:', e)
    else:
        return unknown_event_type

    return {
        "statusCode": 200,
        "headers": response_headers
    }

app.include_router(router, prefix=API_V1_STR)
handler = Mangum(app)
