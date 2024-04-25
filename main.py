from fastapi import FastAPI
from config.database import Base, engine
import user.model
from user.controller import router as user_router

app = FastAPI()

app.include_router(user_router, prefix='/users')

Base.metadata.create_all(bind=engine)

@app.get('/')
async def home():
    return {'message': 'HR API v0.0.1'}


