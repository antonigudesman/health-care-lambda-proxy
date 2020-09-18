import os

from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

import datetime
import boto3
import stripe


BUCKET_NAME = os.environ.get('USER_FILES_BUCKET')
MAX_FILE_SIZE = os.environ.get('MAX_FILE_SIZE', 5)

dynamodb = boto3.resource('dynamodb', region_name='us-east-1', endpoint_url=os.getenv('ENDPOINT_URL'))

table = dynamodb.Table(os.environ.get('TABLE', 'medicaid-details'))
custom_price_table = dynamodb.Table(os.environ.get('CUSTOM_PRICE_TABLE', 'TurbocaidCustomPrice-sps-dev-1'))
stripe_price_table = dynamodb.Table(os.environ.get('STRIPE_PRICE_TABLE', 'TurbocaidStripePrice-sps-dev-1'))
payment_details_table = dynamodb.Table(os.environ.get('STRIPE_PAYMENT_DETAILS_TABLE', 'StripePaymentDetails-sps-dev-1'))

s3 = boto3.resource('s3')

ses = boto3.client('ses', region_name='us-east-1')


def update_dynamodb(email, application_uuid, key, val):
    resp = table.update_item(
        Key={'email': email, 'application_uuid': application_uuid},
        ExpressionAttributeNames={ "#the_key": key },
        ExpressionAttributeValues={ ":val_to_update": val },
        UpdateExpression="SET #the_key = :val_to_update"
    )

    return resp


def update_custom_price_dynamodb(email, key, val):
    resp = custom_price_table.update_item(
        Key={'email': email},
        ExpressionAttributeNames={ "#the_key": key },
        ExpressionAttributeValues={ ":val_to_update": val },
        UpdateExpression="SET #the_key = :val_to_update"
    )

    return resp


def get_price_detail(email):
    try:
        record = custom_price_table.get_item(
            Key={
                'email': email
            },
            ConsistentRead=True,
            ReturnConsumedCapacity='NONE',
        )['Item']
    except KeyError:
        record = stripe_price_table.scan(
            ConsistentRead=True,
            ReturnConsumedCapacity='NONE',
            FilterExpression='standard = :standard',
            ExpressionAttributeValues={':standard': 1}
        )['Items'][0]
        
    return record


def eliminate_sensitive_info(record):
    if 'documents' in record:
        _documents = []
        for ii in record['documents']:
            try:
              ii.pop('s3_location')
            except KeyError as err:
              print('ERROR : no s3 location')  
            _documents.append(ii)
        record['documents'] = _documents

    return record


def get_details(email, application_uuid):
    record = table.get_item(
        Key={
            'email': email, 'application_uuid': application_uuid
        },
        ConsistentRead=True,
        ReturnConsumedCapacity='NONE',
    )
    print(f'the record is str({record})')
    resp = {
        'Item': eliminate_sensitive_info(record['Item']),
        'ResponseMetadata': record['ResponseMetadata']
    }

    print(f'the get details response is {str(resp)}')

    return resp


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


def handle_successful_payment(checkout_session):    
    try:
        email = checkout_session.customer_email
    except AttributeError:
        email = checkout_session.charges.data[0].billing_details.email
    application_uuid = checkout_session.metadata.application_uuid
    
    save_payment_info(email, application_uuid, checkout_session)
    send_completed_application_email(email, application_uuid)
    update_application_status(email, application_uuid)


def get_file_size(b64string):
    raw_size = (len(b64string) * 3) / 4 - b64string.count('=', -2)
    mb_size = raw_size / 1024 / 2014

    return mb_size


def send_email(subject, to_emails, body, attachment_string=None):
    message = MIMEMultipart()
    message['Subject'] = subject
    message['From'] = os.environ.get('SENDER_EMAIL', 'ltclakewooddev@gmail.com')
    message['To'] = to_emails
    # message body
    part = MIMEText(body, 'html')
    message.attach(part)
    # attachment
    if attachment_string:
        part = MIMEApplication(str.encode(attachment_string))
        part.add_header('Content-Disposition', 'attachment', filename='turbocaid_submit.csv')
        message.attach(part)

    resp = ses.send_raw_email(
        Source=message['From'],
        Destinations=to_emails.split(','),
        RawMessage={
            'Data': message.as_string()
        }
    )

    return resp


# def build_csv(data):
#     resp = ''
#     for section, val in data.items():
#         if resp:
#             resp += '\n' * 3

#         resp += section + '\n'

#         for question, sval in val.items():
#             if question != 'undefined':
#                 val = sval.get('val') or ''
#                 resp += f'"{question}","{val}"\n'

#             if sval['sublist']:
#                 for row in sval['sublist']:
#                     _row = [""] + [f'"{ii}"' for ii in row]
#                     resp += f'{",".join(_row)}\n'

#     return resp

def send_completed_application_email(user_email, application_uuid):
    try: 
        subject = 'Turbocaid Application Summary'
        to_emails = os.environ.get('TO_EMAILS', 'jason.5001001@gmail.com')
        applicant_first_name = get_db_value(user_email, 'applicant_info.first_name', application_uuid)['value']
        applicant_last_name = get_db_value(user_email, 'applicant_info.last_name', application_uuid)['value']
        email_body = f'{applicant_first_name} {applicant_last_name} submitted application. Email: {user_email}. Application Id: {application_uuid}'

        resp = send_email(subject, to_emails, email_body)
    except Exception as err:
        print('Error sending email with completed application info ' + str(err))


def update_application_status(user_email, application_uuid):
    try:
        key_to_update = 'submitted_date'
        now = datetime.datetime.now().isoformat()

        resp = update_dynamodb(user_email, application_uuid, key_to_update, now)

        return resp        
    except Exception as err:
        print('Error updating application status ' + str(err))


def save_payment_info(user_email, application_uuid, checkout_session):
    try:
        payment_intent = stripe.PaymentIntent.retrieve(
            checkout_session.payment_intent
        )
        resp = payment_details_table.update_item(
            Key={'email': user_email, 'application_uuid': application_uuid},
            ExpressionAttributeNames={ "#the_key": 'details' },
            ExpressionAttributeValues={ ":val_to_update": payment_intent },
            UpdateExpression="SET #the_key = :val_to_update"
        )    
    except Exception as err:
        print('Error retrieving and saving stripe payment info ' + str(err))

