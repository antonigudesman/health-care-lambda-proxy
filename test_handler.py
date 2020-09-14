from handler import update_details, get_details, upload_file, BUCKET_NAME, get_applications
import boto3
import pytest
import stripe
import os

EMAIL = 'jasonh@ltccs.com'
APPLICATION_UUID = '098029483-sdfsf-234243-009023424'


@pytest.fixture
def clear_data():
    if os.getenv('IS_CODE_DEPLOY_TEST'):
      dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    else:   
      dynamodb = boto3.resource('dynamodb', region_name='us-east-1', endpoint_url='http://localhost:8000')
    table = dynamodb.Table('medicaid-details-unit-test')
    table.delete_item(
        Key={
            'email': EMAIL,
            'application_uuid': APPLICATION_UUID
        }
    )

    table.put_item(
        Item={
            'email': EMAIL,
            'application_uuid': APPLICATION_UUID,
            'documents': []
        }
    )

@pytest.fixture
def clean_bucket():
    ...
    #s3 = boto3.resource('s3')
    #bucket = s3.Bucket(BUCKET_NAME)
    # suggested by Jordon Philips
    #bucket.objects.all().delete()


def test_update_details_non_list_value(clear_data):
    VAL_TO_UPDATE = 'Shprintzah'
    event_body = {
        "action": "update-details",
        "key_to_update": "spouse_info_first_name",
        "value_to_update": {
            "value": VAL_TO_UPDATE
        },
        "application_uuid": APPLICATION_UUID
    }

    update_details(EMAIL, event_body)
    resp = get_details(EMAIL, APPLICATION_UUID)

    assert resp['Item']['email'] == EMAIL
    spouse_first_name_detail = resp['Item']['spouse_info_first_name']
    assert spouse_first_name_detail['value'] == VAL_TO_UPDATE
    length_of_normal_uuid = 32
    assert len(spouse_first_name_detail['uuid']) == length_of_normal_uuid

    SECOND_VAL_TO_UPDATE = 'Yentah'
    second_event_body = {
        "action": "update-details",
        "application_uuid":APPLICATION_UUID,
        "key_to_update": "spouse_info_first_name",
        "value_to_update": {
            "value": SECOND_VAL_TO_UPDATE
        }
    }

    update_details(EMAIL, second_event_body)
    resp2 = get_details(EMAIL,APPLICATION_UUID)

    assert resp['Item']['email'] == EMAIL
    spouse_first_name_detail2 = resp2['Item']['spouse_info_first_name']
    assert spouse_first_name_detail2['value'] == SECOND_VAL_TO_UPDATE

    # make sure the uuid and created date didn't change but updated date did
    assert spouse_first_name_detail2['uuid'] == spouse_first_name_detail['uuid']
    assert spouse_first_name_detail2['created_date'] == spouse_first_name_detail['created_date']
    assert spouse_first_name_detail2['updated_date'] != spouse_first_name_detail['updated_date']


def test_update_details_list_value(clear_data):
    VAL_TO_UPDATE = [
        {
            'value': {
                'name': 'Albert Einstein',
                'moustache_length': 'normal',
                'intelligence': 'very high'
            }
        },
        {
            'value': {
                'name': 'Yosemite Sam',
                'moustache_length': 'very long',
                'intelligence': 'not high'
            }
        },
        {
            'value': {
                'name': 'Mark Twain',
                'moustache_length': 'long',
                'intelligence': 'high'
            }
        }
    ]

    event_body = {
        "action": "update-details",
        "key_to_update": "contacts",
        "value_to_update": VAL_TO_UPDATE,
        "application_uuid":APPLICATION_UUID
    }

    update_details(EMAIL, event_body)
    resp = get_details(EMAIL,APPLICATION_UUID)

    resp_contacts = resp['Item']['contacts']

    assert resp['Item']['email'] == EMAIL

    assert len(resp_contacts) == 3

    for contact in resp_contacts:
        assert len(contact['uuid']) == 32

    first_contact_uuid = resp_contacts[0]['uuid']

    with_new_contact = resp_contacts + [{
        'value': {
            'name': 'Yehuda Herzig',
            'moustache_length': 'usually normal',
            'intelligence': 'usually normal, today not so much'
        }
    }]

    VAL_TO_UPDATE_2 = with_new_contact

    event_body_2 = {
        "action": "update-details",
        "key_to_update": "contacts",
        "value_to_update": VAL_TO_UPDATE_2,
        "application_uuid":APPLICATION_UUID
    }

    update_details(EMAIL, event_body_2)
    resp2 = get_details(EMAIL,APPLICATION_UUID)

    resp_contacts2 = resp2['Item']['contacts']

    assert resp_contacts2[0]['uuid'] == first_contact_uuid

    assert len(resp_contacts2) == 4


def test_file_upload(clear_data, clean_bucket):
    event_body_1 = {
        'file_name': 'the_very_very_awesomely_cool_file.jpg',
        'document_type': 'birth_certificate',
        'associated_medicaid_detail_uuid': '54321',
        'file_contents':'I was born way back in 1842',
        "application_uuid":APPLICATION_UUID
    }

    upload_file(EMAIL,event_body_1)

    event_body_2 = {
        'file_name': 'muncatcher_passport.jpg',
        'document_type': 'passport',
        'associated_medicaid_detail_uuid': '12345',
        'file_contents':'Appears to be blank',
        "application_uuid":APPLICATION_UUID
    }

    upload_file(EMAIL, event_body_2)

    resp = get_details(EMAIL,APPLICATION_UUID)

    document_resp = resp['Item']['documents']

    assert len(document_resp)==2

    assert document_resp[0]['document_name']=='the_very_very_awesomely_cool_file.jpg'

    assert document_resp[1]['associated_medicaid_detail_uuid'] == '12345'

    assert document_resp[1]['uuid'] is not None

    assert document_resp[0]['s3_location'] is not None

def test_get_applications():
    resp = get_applications(EMAIL)
    assert resp == 'howdy'

def test_create_payment_session():
    try:
        kms = boto3.client('kms')
        stripe_api_key = kms.decrypt(CiphertextBlob=base64.b64decode(os.getenv('STRIPE_API_KEY')))['Plaintext'].decode()
    except Exception as err:
        stripe_api_key = 'sk_test_51GqKSqJZ3xWggisxmSskl1KjsrlbiiYxH0tgv7KqGjHmlXHV5221Kc4sB7AKNfls0wHdQRKNA1sE8vSAXBHv3WiD00Eut0EXCa'
    stripe.api_key = stripe_api_key

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price': 'price_1GrxPUJZ3xWggisxoZt4yYmW',
            'quantity': 1,
        }],
        mode='payment',
        client_reference_id=APPLICATION_UUID,
        success_url='https://localhost:3006/success',
        cancel_url='https://localhost:3006/cancel',
    )
    assert session is not None
    assert session.client_reference_id == APPLICATION_UUID
    return session


def test_handle_checkout_session_succeeded():
    try:
        kms = boto3.client('kms')
        stripe_api_key = kms.decrypt(CiphertextBlob=base64.b64decode(os.getenv('STRIPE_API_KEY')))['Plaintext'].decode()
    except Exception as err:
        stripe_api_key = 'sk_test_51GqKSqJZ3xWggisxmSskl1KjsrlbiiYxH0tgv7KqGjHmlXHV5221Kc4sB7AKNfls0wHdQRKNA1sE8vSAXBHv3WiD00Eut0EXCa'
    stripe.api_key = stripe_api_key
    # application_uuid = checkout_session.client_reference_id
    # payment_intent_id = checkout_session.payment_intent_id
    payment_intent = stripe.PaymentIntent.retrieve(
        'pi_1Gv4jbJZ3xWggisxN0kedb0n'
    )
    assert payment_intent.amount == 20000;
    assert payment_intent.status == "requires_payment_method"
