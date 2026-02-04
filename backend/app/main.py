from fastapi import FastAPI
from ..app.db import engine
from ..app.models import SQLModel

app = FastAPI()

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

@app.get("/")
def root():
    return {"status": "ok"}
