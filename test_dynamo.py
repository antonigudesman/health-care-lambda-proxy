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


# def test_get_details(clear_data):
#     resp = get_details(EMAIL)
#     assert resp == "purple octopus"


def test_update_details(clear_data):
    event_body = {
        "action": "update-details",
        "key_to_update": "spouse_info_first_name",
        "value_to_update": "Shprintzah"
    }

    update_details(EMAIL, event_body)
    resp = get_details(EMAIL)

    assert resp['Item']['email'] == EMAIL
    assert resp['Item']['spouse_info_first_name'] == 'Shprintzah'
