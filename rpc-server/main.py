from fastapi import FastAPI

from routers import rpc_router

app = FastAPI()
app.include_router(rpc_router)
