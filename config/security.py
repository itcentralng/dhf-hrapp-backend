import os
from passlib.hash import pbkdf2_sha256
from jose import jwt, JWTError
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from user import schema
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, status, HTTPException
from config.config import get_db
from user import utils

SECRET_KEY = os.environ.get("SECRET_KEY")
ACCESS_TOKEN_EXPIRE_MINUTES = os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES")

oauthSchema = OAuth2PasswordBearer(tokenUrl='user/login')

def hash_string(plain_text: str) -> str:
    return pbkdf2_sha256.hash(plain_text)


def verify_hash(plain_text, hashed_password):
    return pbkdf2_sha256.verify(plain_text, hashed_password)


def generate_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now() + timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({'exp': expire})
    encoded_token = jwt.encode(to_encode, SECRET_KEY)
    return encoded_token



def verify_access_token(token: str, exception):
    try:
        token = token.replace('Bearer ','')
        payload = jwt.decode(token, SECRET_KEY)
        id: str = payload.get('user_id')
        if id is None:
            raise exception
        token_data = schema.TokenData(id=id)
    except JWTError:
        raise exception
    return token_data


def get_current_user(token: str = Depends(oauthSchema)):
    exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"could not verify cred", headers={"WWW-Authenticate": "Bearer"})
    token_data = verify_access_token(token, exception)
    return token_data
