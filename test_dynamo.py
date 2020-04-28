from handler import update_details, get_details


def test_update_details():
    email = 'jasonh@ltccs.com'
    event_body = {
        "action": "update-details",
        "key_to_update": "spouse_info_first_name",
        "value_to_update": "Shprintzah"
    }


    update_details(email, event_body)
    resp = get_details(email)
    assert resp['Item']['email']=='jasonh@ltccs.com'
    assert resp['Item']['spouse_info_first_name']=='Shprintzah'

