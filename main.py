from dotenv import load_dotenv
load_dotenv() 

import os 
from models import TrafficReportResponse
from fastapi import FastAPI, HTTPException, Header, Security, Depends
from starlette.status import HTTP_403_FORBIDDEN
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import FileResponse
import express_traffic_report_service as traffic_service
from fastapi.staticfiles import StaticFiles
from database_helpers_postgres import initialize_database
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(lifespan=lifespan)
api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == os.environ.get("API_KEY"):
        return api_key
    else:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, 
            detail="Could not validate API key"
        )



@app.get("/api/traffic-report")
def get_traffic_report(api_key: str = Depends(get_api_key)) -> TrafficReportResponse:
    return traffic_service.get_latest_traffic_report()

@app.get("/api/traffic-report/mp3/{recording_name}")
def get_traffic_report_mp3(recording_name: str, api_key: str = Depends(get_api_key)):
    mp3_response = traffic_service.get_traffic_report_mp3(recording_name)
    if mp3_response:
        return mp3_response
    raise HTTPException(status_code=404, detail="Recording not found")

@app.get("/")
def get_root():
    return FileResponse("static/index.html")