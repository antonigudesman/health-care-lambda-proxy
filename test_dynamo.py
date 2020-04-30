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


