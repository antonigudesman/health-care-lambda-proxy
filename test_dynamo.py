from handler import update_details, get_details
import boto3
import pytest

EMAIL = 'jasonh@ltccs.com'
APPLICATION_NAME = 'my_application'


@pytest.fixture
def clear_data():
    endpoint_url = 'http://localhost:8000'
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1', endpoint_url=endpoint_url)
    table = dynamodb.Table('medicaid-details')
    table.delete_item(
        Key={
            'email': EMAIL,
            'application_name': APPLICATION_NAME
        }
    )

    table.put_item(
        Item={
            'email': EMAIL,
            'application_name': APPLICATION_NAME
        }
    )


# def test_get_details(clear_data):
#     resp = get_details(EMAIL)
#     assert resp == "purple octopus"


def test_update_details_non_list_value(clear_data):
    VAL_TO_UPDATE = 'Shprintzah'
    event_body = {
        "action": "update-details",
        "key_to_update": "spouse_info_first_name",
        "value_to_update": {
            "value": VAL_TO_UPDATE
        }
    }

    update_details(EMAIL, event_body)
    resp = get_details(EMAIL)

    assert resp['Item']['email'] == EMAIL
    spouse_first_name_detail = resp['Item']['spouse_info_first_name']
    assert spouse_first_name_detail['value'] == VAL_TO_UPDATE
    length_of_normal_uuid = 32
    assert len(spouse_first_name_detail['uuid']) == length_of_normal_uuid

    SECOND_VAL_TO_UPDATE = 'Yentah'
    second_event_body = {
        "action": "update-details",
        "key_to_update": "spouse_info_first_name",
        "value_to_update": {
            "value": SECOND_VAL_TO_UPDATE
        }
    }

    update_details(EMAIL, second_event_body)
    resp2 = get_details(EMAIL)

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
        "value_to_update": VAL_TO_UPDATE
    }

    update_details(EMAIL, event_body)
    resp = get_details(EMAIL)

    resp_contacts = resp['Item']['contacts']

    assert resp['Item']['email'] == EMAIL

    assert len(resp_contacts)==3

    for contact in resp_contacts:
        assert len(contact['uuid'])==32

    first_contact_uuid = resp_contacts[0]['uuid']

    with_new_contact = resp_contacts + [{
            'value': {
                'name': 'Yehuda Herzig',
                'moustache_length': 'usually normal',
                'intelligence': 'usually normal, today not so much'
            }
        }]

    VAL_TO_UPDATE_2 =  with_new_contact

    event_body_2 = {
        "action": "update-details",
        "key_to_update": "contacts",
        "value_to_update": VAL_TO_UPDATE_2
    }

    update_details(EMAIL, event_body_2)
    resp2 = get_details(EMAIL)

    resp_contacts2 = resp2['Item']['contacts']

    assert resp_contacts2[0]['uuid'] == first_contact_uuid

    assert len(resp_contacts2) == 4


