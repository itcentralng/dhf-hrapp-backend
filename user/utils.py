from sqlalchemy.orm import Session
from user import model
from user import schema
from config import security


def get_user(db: Session, user_id):
    try:
        user = db.query(model.User).filter(model.User.id == user_id).first()
        return True, user
    except Exception as e:
        return False, e

def create_user(db: Session, user: schema.CreateUser):
    try:
        hash_password = security.hash_string(user.password)

        result = model.User(first_name = user.first_name, last_name = user.last_name, email = user.email, password = hash_password, phone = user.phone)
        db.add(result)
        db.commit()
        db.refresh(result)
        return result
    except Exception as e:
        return False, e

def get_user_by_email(db: Session, email: str):
    try:
        return db.query(model.User).filter(model.User.email == email).first()
    except Exception as e:
        return False, e

def change_password(db: Session, password: str, id):
    try:
        hash_password = security.hash_string(password)
        result = db.query(model.User).filter(model.User.id == id)
        result.update({'password': hash_password}, synchronize_session = False)
        db.commit()
        result.first()
        return True
    except Exception as e:
        return False