import sqlite3
from flask import current_app as app

DB_FILE = "chatbot_data.db"  # make sure this matches your DB path

def fetch_appointments_from_db():
    """Fetch all booked appointments from the database."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT patient_name, doctor, date, time, status 
                FROM appointments 
                WHERE status = 'booked'
            """)
            rows = cursor.fetchall()
            print("Fetched rows:", rows)
            appointments = [
                {
                    "patient_name": r[0],
                    "doctor": r[1],
                    "date": r[2],
                    "time": r[3],
                    "status": r[4]
                } for r in rows
            ]
            return appointments
    except Exception as e:
        app.logger.error(f"Error fetching appointments: {e}")
        return []
