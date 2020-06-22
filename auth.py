import os

from datetime import datetime

from jose import jwt
from jwt_utils import get_jwks, verify_jwt
from response_helpers import (
    InvalidTokenError,
    ExpiredTokenError
)


DEV_JWKS_URL = 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_c1urqyqMM/.well-known/jwks.json'
JWKS_URL = os.environ.get('JWKS_URL', DEV_JWKS_URL)


def get_claims(event_body):
    jwks = get_jwks(JWKS_URL)
    id_token = event_body['id_token']

    if not verify_jwt(id_token, jwks):
        raise InvalidTokenError

    claims = jwt.get_unverified_claims(id_token)

    if datetime.now().timestamp() > claims['exp']:
        raise ExpiredTokenError

    return claims


def get_email(event_body):
    try:
        claims = get_claims(event_body)
        return claims["cognito:username"]
    except Exception as e:
        pass
