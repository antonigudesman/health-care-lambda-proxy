import datetime
import uuid


class InvalidUuidError(Exception):
    pass


class MedicaidDetail:
    def __init__(self,  value,  updated_date, the_uuid=None, created_date=None):
        self.uuid = the_uuid
        self.created_date = created_date
        self.updated_date = updated_date
        self.value = value


def convert_to_medicaid_details_list(key_to_update, value_to_update, val_from_db):
    dict_of_db_vals = {item['uuid']: item for item in val_from_db} if val_from_db else {}

    # dict_by_uuid = {}  # {'u8982-w98rw9r': {theitemfromdb}}
    # for medicaid_detail in db_list:
    #     dict_by_uuid[medicaid_detail['uuid']] = medicaid_detail

    now = datetime.datetime.now().isoformat()

    medicaid_details_to_insert = []
    for detail_item_to_update in value_to_update:

        medicaid_detail = MedicaidDetail(updated_date=now, value=detail_item_to_update['value'])

        if 'uuid' in detail_item_to_update:
            the_uuid = detail_item_to_update['uuid']
            try:
                db_item = dict_of_db_vals[the_uuid]
            except KeyError as err:
                print(f'could not find corresponding item in db with uuid {the_uuid}')
                raise InvalidUuidError
            medicaid_detail.uuid = the_uuid
            medicaid_detail.created_date = db_item['created_date']
        else:
            medicaid_detail.uuid = uuid.uuid4().hex
            medicaid_detail.created_date = datetime.datetime.now().isoformat()

        medicaid_details_to_insert.append(medicaid_detail.__dict__)

    return medicaid_details_to_insert


def convert_to_medicaid_detail(key_to_update, value_to_update, val_from_db):
    now = datetime.datetime.now().isoformat()
    medicaid_detail = MedicaidDetail(updated_date=now, value=value_to_update['value'])
    if val_from_db:
        medicaid_detail.uuid = val_from_db['uuid']
        medicaid_detail.created_date = val_from_db['created_date']
    else:
        medicaid_detail.uuid = uuid.uuid4().hex
        medicaid_detail.created_date = now

    return medicaid_detail.__dict__