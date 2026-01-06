import requests
from bs4 import BeautifulSoup
import base64
from openai import OpenAI
import json
import os
import prompts
from models import TrafficReportStatements, TrafficReportStatementCategorization, TrafficReportCategorizationResponse, TrafficReportResponse, TrafficReportDataStorageModel
import database_helpers_postgres as db_helpers
import logging
from fastapi.responses import FileResponse

logger = logging.getLogger('uvicorn')

MP3_DOWNLOAD_DESTINATION = 'downloaded_mp3s'

def __get_mp3_download_links() -> list[str] | None:
    url = "https://www.expres.sk/kategoria/dopravny-servis"

    try:
        logger.info(f"Downloading traffic report from {url}")
        # Make the request
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes

        # Parse the HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the DIV with data-podcast attribute
        div_with_podcast = soup.find('div', {'data-podcast': True})

        if div_with_podcast is None:
            logger.info("No DIV with data-podcast attribute found.")
            return None

        # Extract the value of data-podcast
        podcast_data = div_with_podcast['data-podcast']

        # Decode from base64
        decoded_data = base64.b64decode(podcast_data)

        # Load as JSON
        json_data = json.loads(decoded_data)
        
        mp3_download_lists = [item_url["url"] for item_url in json_data["list"]]
        
        return mp3_download_lists
    except (ValueError, KeyError) as e:
        print(f"Error parsing data: {e}")
        return None

def __download_traffic_report(download_link: str) -> str | None:
    if not os.path.exists(MP3_DOWNLOAD_DESTINATION):
        os.makedirs(MP3_DOWNLOAD_DESTINATION)
    try:
        logger.info(f"Downloading MP3 from {download_link}")
        filename = os.path.basename(download_link)
        filepath = os.path.join(MP3_DOWNLOAD_DESTINATION, filename)
        if os.path.exists(filepath):
            logger.info(f"File {filename} already exists. Skipping download.")
            return os.path.abspath(filepath)
        response = requests.get(download_link)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(response.content)
        return os.path.abspath(filepath)
    except requests.RequestException as e:
        logging.exception(f"Error downloading {download_link}")
        return None

def __transcribe_audio(file_path: str) -> str:
    recording_name = os.path.basename(file_path)
    logger.info(f"Transcribing audio file {recording_name}")
    client = OpenAI()
    audio_file= open(file_path, "rb")
    transcription = client.audio.transcriptions.create(
        model="gpt-4o-transcribe", 
        file=audio_file
    )
    raw_transcription = transcription.text
    # The transcription is now mostly bad with typos, so we need to fix it
    fix_transcription_response = client.chat.completions.create(
      model="gpt-4.1-mini",
        #temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": prompts.FIX_TRANSCRITION_ERRORS_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": raw_transcription
            }
        ]
    )
    fixed_transcription = fix_transcription_response.choices[0].message.content
    return fixed_transcription

def __split_transcription_into_statements(transcription: str) -> list[str]:
    logger.info("Splitting transcription into statements.")
    client = OpenAI()
    response = client.chat.completions.parse(
      model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": prompts.SPLIT_TRANSCRIPTION_INTO_STATEMENTS_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": transcription
            }
        ],
        response_format=TrafficReportStatements
    )
    result: TrafficReportStatements = response.choices[0].message.parsed
    return result.statements

def __categorize_statement(statements: list[str]) -> list[TrafficReportStatementCategorization]:
    logger.info(f"Categorizing statement.")
    client = OpenAI()
    response = client.chat.completions.parse(
      model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": prompts.CATEGORIZE_STATEMENTS_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": '\n'.join(statements)
            }
        ],
        response_format=TrafficReportCategorizationResponse
    )
    result: TrafficReportCategorizationResponse = response.choices[0].message.parsed
    return result.categorizations

def __get_already_processed_report(mp3_name: str) -> TrafficReportResponse | None:
    existing_data = db_helpers.retrieve_traffic_report_data(mp3_name)
    if not existing_data:
        return None
    _, recording_data, created_at = existing_data
    return TrafficReportResponse(
        recording_name=mp3_name,
        transcription=recording_data.transcription,
        statements=recording_data.statements,
        created_at=str(created_at) if created_at else None
    )

def get_latest_traffic_report() -> TrafficReportResponse:
    mp3_download_links = __get_mp3_download_links()
    if not mp3_download_links:
        raise ValueError("No MP3 download links found")
    main_mp3_link = mp3_download_links[0]
    main_mp3_name = os.path.basename(main_mp3_link)
    existing_report = __get_already_processed_report(main_mp3_name)
    if existing_report:
        logger.info(f"Using cached traffic report for {existing_report.recording_name}")
        return existing_report
    main_mp3_path = __download_traffic_report(main_mp3_link)
    if not main_mp3_path:
        raise ValueError("Failed to download MP3")
    transcription = __transcribe_audio(main_mp3_path)
    statements = __split_transcription_into_statements(transcription)
    categorizations = __categorize_statement(statements)
    store_object = TrafficReportDataStorageModel(
        transcription=transcription,
        statements=categorizations
    )
    created_at = db_helpers.store_traffic_report_data(main_mp3_name, store_object)
    traffic_report_response = TrafficReportResponse(
        recording_name=main_mp3_name,
        transcription=transcription,
        statements=categorizations,
        created_at=str(created_at) if created_at else None
    )
    return traffic_report_response

def get_traffic_report_mp3(recording_name: str) -> FileResponse | None:
    abs_path = os.path.join(MP3_DOWNLOAD_DESTINATION, recording_name)
    if os.path.exists(abs_path):
        return FileResponse(abs_path, media_type='audio/mpeg', filename=recording_name)
    return None
