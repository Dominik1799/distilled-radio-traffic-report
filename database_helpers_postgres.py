import os
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor, Json
from models import TrafficReportDataStorageModel

# Database connection parameters from environment variables
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'traffic-report')
DB_USER = os.getenv('DB_USERNAME', 'user')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')

def __get_connection():
    """Establish a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
# I know its not ideal to store it this way but for this small project its fine
# plus its running on a very small VM instance so I have a single DB for everything
def initialize_database():
    """Create the traffic_reports table if it doesn't exist."""
    with __get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS traffic_report (
                    recording_name VARCHAR PRIMARY KEY,
                    recording_data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

def retrieve_traffic_report_data(recording_name: str) -> tuple[str, TrafficReportDataStorageModel, datetime] | None:
    """Retrieve data for a specific recording."""
    with __get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM traffic_report WHERE recording_name = %s", (recording_name,))
            row = cur.fetchone()
            if row:
                return row["recording_name"], TrafficReportDataStorageModel(**row["recording_data"]), row["created_at"]
            return None
        

def store_traffic_report_data(recording_name: str, recording_data: TrafficReportDataStorageModel) -> str:
    """Store or update recording_data for a specific recording and return the generated timestamp."""
    serializable_data = recording_data.model_dump(mode="json")
    with __get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO traffic_report (recording_name, recording_data) 
                VALUES (%s, %s)
                ON CONFLICT (recording_name) 
                DO UPDATE SET recording_data = EXCLUDED.recording_data
                RETURNING created_at
                """,
                (recording_name, Json(serializable_data))
            )
            # fetch the timestamp returned by RETURNING
            created_at = cur.fetchone()[0]
            conn.commit()
            return created_at