import base64
import datetime

import stripe
import requests

from requests.auth import HTTPBasicAuth
from typing import Dict
from typing import Optional
from mangum import Mangum
from fastapi import APIRouter, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from boto3.dynamodb.conditions import Key

from config import API_V1_STR, PROJECT_NAME, SECTION_LIST
from auth import get_email
from utils import *
from medicaid_detail_utils import *
from response_helpers import (
    response_headers, missing_file_contents, missing_file_name,
    invalid_token, forbidden_action, options_response, missing_files, 
    invalid_signature, unknown_event_type, invalid_request,
    max_file_size_exceeded, invalid_checkout_session, incorrect_price
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
    stripe.api_key = kms.decrypt(CiphertextBlob=base64.b64decode(os.getenv('STRIPE_API_KEY')))['Plaintext'].decode()
except Exception as err:
    stripe.api_key = os.getenv('STRIPE_API_KEY')


@router.post('/get-applications')
def get_applications(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token

    response = table.query(
        KeyConditionExpression=Key('email').eq(user_email)
    )

    resp = [eliminate_sensitive_info(ii) for ii in response['Items']]

    return resp


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
        tags = file.get('tags', [])
        if not file_name:
            return missing_file_name

        if not file_contents or file_contents == 'data:':
            return missing_file_contents

        if get_file_size(file_contents) > MAX_FILE_SIZE:
            return max_file_size_exceeded

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
                             the_uuid=create_uuid(),
                             tags=tags
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

    verified_price = get_price_detail(user_email)
    if verified_price['price_id'] != event_body['price_id']:
        print('Error verifying price')
        return incorrect_price

    react_app_url = os.getenv('REACT_APP_URL')
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': verified_price['price_id'],
                'quantity': 1
            }],
            mode='payment',
            client_reference_id= event_body['application_uuid'],
            success_url=f'{react_app_url}/success?sessionId={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{react_app_url}/intake',
            customer_email=user_email
        )

        return session.id
    except stripe.error.InvalidRequestError as e: 
        print('Error creating checkout session:' + str(e))
        return invalid_checkout_session


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
    except stripe.error.SignatureVerificationError:
        return invalid_signature

    if event.type == 'checkout.session.completed':
        try:
            checkout_session = event.data.object
            handle_successful_payment(checkout_session)
        except Exception as e:
            print('Error handling successful checkout session:', e)
    else:
        return unknown_event_type

    return {
        "statusCode": 200,
        "headers": response_headers
    }


@router.post('/get-files')
def get_files(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token
    application_uuid = event_body['application_uuid']
    uuid = event_body['uuid']

    documents = get_details(user_email, application_uuid)['Item']['documents']
    resp = []
    for doc in documents:
        if doc['associated_medicaid_detail_uuid'] != uuid:
            continue

        file_name = doc['document_name']
        full_file_name = f'{user_email}/{application_uuid}/{doc["document_type"]}/{file_name}'
        image = s3.Object(BUCKET_NAME, full_file_name).get()['Body'].read()

        item = {
            'document_name': file_name,
            'image': base64.b64encode(image)
        }

        resp.append(item)

    return resp

'''
Endpoints for docusign
'''
@router.post('/check-signed')
def check_signed(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token

    # get access token
    ds_client_id = os.getenv("DS_CLIENT_ID")
    ds_client_secret = os.getenv("DS_CLIENT_SECRET")
    refresh_token = os.getenv("DS_REFRESH_TOKEN")

    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }

    auth_url = 'https://account-d.docusign.com/oauth/token'

    resp = requests.post(auth_url, data=data, auth=HTTPBasicAuth(ds_client_id, ds_client_secret)).json()

    access_token = resp['access_token']
    print ('ds access token:', access_token)

    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    account_id = os.getenv('DS_ACCOUNT_ID')
    body = event_body['value_to_update']
    envelope_id = body['envelope']
    recipient_id = body['recipient']

    # get recipients
    params = {
        'include': 'recipients'
    }
    base_url = os.getenv('DS_BASE_URL')
    url = base_url + f'/restapi/v2.1/accounts/{account_id}/envelopes/{envelope_id}/recipients'
    resp = requests.get(url, headers=headers, params=params).json()

    status = ''
    for ii in resp['signers']:
        if ii['recipientIdGuid'] == recipient_id:
            status = ii['status']

    application_uuid = event_body['application_uuid']
    key_to_update = 'docusign'
    body['status'] = status

    now = datetime.datetime.now().isoformat()
    user_info = UserInfo(created_date=now, updated_date=now, value=body)

    update_dynamodb(user_email, application_uuid, key_to_update, user_info.__dict__)

    return status


'''
Endpoints for the summary portal
'''
@router.post('/get-users')
def get_users(event_body: Dict, order_by: str, page: int, page_size: int, q: Optional[str] = ''):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token

    internal_users = os.getenv('INTERNAL_USERS', '').split(',')
    if user_email not in internal_users:
        return forbidden_action

    q = q.lower()
    resp = table.scan()
    items = []

    for ii in resp['Items']:
        item = {
            'email': ii['email'],
            'submitted_date': ii.get('submitted_date', ''),
            'first_name': ii['applicant_info.first_name']['value'] if 'applicant_info.first_name' in ii else '',
            'last_name': ii['applicant_info.last_name']['value'] if 'applicant_info.last_name' in ii else ''
        }

        if any([q in item['email'].lower(), q in item['first_name'].lower(), q in item['last_name'].lower()]):
            items.append(item)

    order_by = order_by.replace('id', 'email')
    if '-' in order_by:
        order_by = order_by.strip('-')
        sorted_items = sorted(items, key=lambda k: k.get(order_by, ''), reverse=True) 
    else:
        sorted_items = sorted(items, key=lambda k: k.get(order_by, '')) 

    resp = {
        'Count': len(items),
        'Items': sorted_items[(page-1)*page_size:page*page_size]
    }

    return resp


@router.post('/get-user')
def get_user(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token

    email = event_body['email']
    response = table.query(
        KeyConditionExpression=Key('email').eq(email)
    )

    item = response['Items'][0]

    inputs = []
    for _inputs in SECTION_LIST:
        inputs += _inputs['inputs']

    result = {
        'email': item.pop('email'),
        'submitted_date': item.pop('submitted_date') if 'submitted_date' in item else '',
        'first_name': item['applicant_info.first_name']['value'] if 'applicant_info.first_name' in item else '',
        'last_name': item['applicant_info.last_name']['value'] if 'applicant_info.last_name' in item else '',
        'items': []
    }

    # handle excludes
    excludes = [
        "sidebarHistory",
        "documents",
        "application_uuid",
        "currentScreenName",
        "application_name"
    ]

    for ii in excludes:
        item.pop(ii, None)

    for key in inputs:
        if key in item:
            result['items'].append({
                'key': key,
                'val': item.pop(key)
            })
        else:
            _item = dict(item)
            for _key in _item:
                if _key.startswith(key):
                    result['items'].append({
                        'key': _key,
                        'val': item.pop(_key)
                    })

    print (item, '*'*10)

    return result


'''
User management with custom prices
'''
@router.post('/get-custom-prices')
def get_custom_prices(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token

    resp = custom_price_table.scan()

    return resp


@router.post('/get-price')
def get_price(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token
    resp = get_price_detail(user_email)

    return resp


@router.post('/create-custom-price')
def create_custom_price(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token

    email = event_body['email']
    price = event_body['price']
    now = datetime.datetime.now().isoformat()

    custom_price_table.put_item(
        Item={
            'email': email,
            'price': price,
            'updated_by': user_email,
            'updated_at': now
        },
        ReturnValues='NONE'
    )

    resp = get_price_detail(email)

    return resp


@router.post('/update-custom-price')
def update_custom_price(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token

    email = event_body['email']
    price = event_body['price']
    now = datetime.datetime.now().isoformat()

    update_custom_price_dynamodb(email, 'price', price)
    update_custom_price_dynamodb(email, 'updated_at', now)
    update_custom_price_dynamodb(email, 'updated_by', user_email)

    resp = get_price_detail(email)

    return resp


@router.post('/delete-custom-price')
def delete_custom_price(event_body: Dict):
    user_email = get_email(event_body)
    if not user_email:
        return invalid_token

    email = event_body['email']
    resp = custom_price_table.delete_item(
        Key={'email': email}
    )

    return resp


app.include_router(router, prefix=API_V1_STR)
handler = Mangum(app)
