from sqlmodel import SQLModel, create_engine, Session
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://intercom:intercom@localhost:5434/intercom"
)

engine = create_engine(DATABASE_URL, echo=True)

def get_session():
    with Session(engine) as s:
        yield s
