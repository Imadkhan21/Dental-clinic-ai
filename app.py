import os
import shutil
import pandas as pd
import sqlite3
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from chatbot_model import get_chat_response  # Make sure chatbot_model.py exists

# === Paths ===

stop_execution_flag = False

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'csv', 'db'}
STATIC_CSV = os.path.join(BASE_DIR, 'patient_details2.csv')  # Default CSV
DB_FILE = os.path.join(BASE_DIR, 'chatbot_data.db')

# === Flask App ===
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'replace_with_your_secret_key'

# === DB Initialization ===
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                        (id INTEGER PRIMARY KEY, message TEXT, response TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS current_file 
                        (id INTEGER PRIMARY KEY, filename TEXT)''')
        conn.commit()

init_db()

# === Cache & Lock ===
data_cache = None
data_lock = threading.Lock()

# === File Utils ===
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_current_file():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM current_file ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
    return result[0] if result else None

def set_current_file(filename):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM current_file")
        cursor.execute("INSERT INTO current_file (filename) VALUES (?)", (filename,))
        conn.commit()

def load_data():
    global data_cache
    current_file = get_current_file()
    if current_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_file)
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path)
                with data_lock:
                    data_cache = df
                print(f"[DATA] Loaded {current_file} into cache")
            except Exception as e:
                print(f"[DATA] Failed to read CSV {file_path}: {e}")
                with data_lock:
                    data_cache = None
        else:
            with data_lock:
                data_cache = None
    else:
        with data_lock:
            data_cache = None

# Change STATIC_CSV path to match where you actually store it in repo
STATIC_CSV = os.path.join(BASE_DIR, 'uploads', 'patient_details2.csv')  

def bootstrap_dataset():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    current = get_current_file()
    current_path = os.path.join(UPLOAD_FOLDER, current) if current else None

    needs_seed = (not current) or (current and not os.path.exists(current_path))

    if needs_seed:
        if os.path.exists(STATIC_CSV):
            dest = os.path.join(UPLOAD_FOLDER, os.path.basename(STATIC_CSV))
            shutil.copy(STATIC_CSV, dest)  # Always overwrite to be safe
            set_current_file(os.path.basename(STATIC_CSV))
            print(f"[INIT] Seed dataset loaded: {dest}")
        else:
            print(f"[INIT] No static CSV found at {STATIC_CSV}")


try:
    bootstrap_dataset()
    load_data()
except Exception as e:
    print(f"[INIT] Bootstrap error: {e}")

# === Routes ===
@app.route('/')
def index():
    current_file = get_current_file()
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message, response FROM chat_history")
        history = cursor.fetchall()
    return render_template('index.html', history=history, filename=current_file)

@app.route('/ask', methods=['POST'])
def ask():
    global stop_execution_flag
    stop_execution_flag = False  # reset at the start of request

    user_input = request.json.get('message')
    with data_lock:
        df = data_cache

    if df is None:
        return jsonify({'response': '⚠ No file uploaded or data loaded. Please upload a CSV first.'})

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message, response FROM chat_history ORDER BY id ASC")
        session_history = cursor.fetchall()

    if stop_execution_flag:
        return jsonify({'status': 'stopped', 'response': None})

    response = get_chat_response(user_input, df, session_history=session_history)

    if stop_execution_flag:
        return jsonify({'status': 'stopped', 'response': None})

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_history (message, response) VALUES (?, ?)", (user_input, response))
        conn.commit()

    return jsonify({'response': response})


@app.route('/stop_execution', methods=['POST'])
def stop_execution():
    global stop_execution_flag
    stop_execution_flag = True
    return jsonify({'status': 'stopped'})


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        file.save(save_path)
        set_current_file(filename)
        load_data()
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("DELETE FROM chat_history")
            conn.commit()
    return redirect(url_for('index'))

@app.route('/delete_file', methods=['POST'])
def delete_file():
    current_file = get_current_file()
    if current_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_file)
        if os.path.exists(file_path):
            os.remove(file_path)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM current_file")
            cursor.execute("DELETE FROM chat_history")
            conn.commit()
        global data_cache
        with data_lock:
            data_cache = None
    return redirect(url_for('index'))

@app.route('/clear_chat', methods=['POST'])
def clear_chat():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM chat_history")
        conn.commit()
    return jsonify({'status': 'cleared'})

from datetime import datetime, timedelta

@app.route('/get_chart_data', methods=['POST'])
def get_chart_data():
    try:
        data = request.json
        days = int(data.get('days', 30))
        chart_type = data.get('chart_type', 'bar')
        
        with data_lock:
            df = data_cache.copy() if data_cache is not None else None
        
        if df is None:
            return jsonify({'error': 'No data loaded. Please upload a CSV file first.'}), 400
        
        # Check for required columns
        required_columns = ['Invoice date', 'description']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({
                'error': f'Missing required columns: {", ".join(missing_columns)}'
            }), 400
        
        # Convert Invoice date to datetime and filter
        df['Invoice date'] = pd.to_datetime(df['Invoice date'], errors='coerce')
        df = df.dropna(subset=['Invoice date'])
        
        # Filter for the specified number of days
        start_date = datetime.now() - timedelta(days=days)
        filtered_df = df[df['Invoice date'] >= start_date]
        
        if filtered_df.empty:
            return jsonify({
                'error': f'No records found in the last {days} days.'
            }), 404
        
        # Aggregate by description
        counts = filtered_df['description'].value_counts().reset_index()
        counts.columns = ['label', 'value']
        
        # Limit to top 10 items for better visualization
        if len(counts) > 10:
            counts = counts.head(10)
            other_count = len(filtered_df) - counts['value'].sum()
            if other_count > 0:
                counts = pd.concat([
                    counts,
                    pd.DataFrame({'label': ['Other'], 'value': [other_count]})
                ], ignore_index=True)
        
        return jsonify({
            'labels': counts['label'].tolist(),
            'values': counts['value'].tolist(),
            'chart_type': chart_type,
            'total_records': len(filtered_df),
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': datetime.now().strftime('%Y-%m-%d')
            }
        })
    
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500
    
    
from datetime import datetime, timedelta
import pandas as pd
from flask import request, jsonify

# Add this route for query data
@app.route('/get_query_data', methods=['POST'])
def get_query_data():
    try:
        data = request.json
        query_type = data.get('query_type')
        query_params = data.get('params', {})
        
        with data_lock:
            df = data_cache.copy() if data_cache is not None else None
        
        if df is None:
            return jsonify({'error': 'No data loaded. Please upload a CSV file first.'}), 400
        
        # Replace NaN values with None
        df = df.where(pd.notnull(df), None)
        
        result = {}
        
        if query_type == 'patients_by_days':
            # Query: How many patients came in the last X days?
            days = int(query_params.get('days', 15))
            
            # Check if 'Invoice date' column exists
            if 'Invoice date' not in df.columns:
                return jsonify({'error': 'CSV must have an "Invoice date" column'}), 400
            
            # Convert to datetime
            df['Invoice date'] = pd.to_datetime(df['Invoice date'], errors='coerce')
            df = df.dropna(subset=['Invoice date'])
            
            # Filter for the specified number of days
            start_date = datetime.now() - timedelta(days=days)
            filtered_df = df[df['Invoice date'] >= start_date]
            
            # Count patients per day
            daily_counts = filtered_df.groupby(filtered_df['Invoice date'].dt.date).size().reset_index(name='count')
            
            result = {
                'labels': [date.strftime('%Y-%m-%d') for date in daily_counts['Invoice date']],
                'values': daily_counts['count'].tolist(),
                'title': f'Patient Count - Last {days} Days',
                'total_patients': len(filtered_df)
            }
            
        elif query_type == 'patients_by_location':
            # Query: How many patients came from a specific location?
            location = query_params.get('location', '')
            
            # Find location column (could be named 'city', 'location', etc.)
            location_column = None
            for col in ['city', 'location', 'address', 'patient_location']:
                if col in df.columns:
                    location_column = col
                    break
            
            if not location_column:
                return jsonify({'error': 'No location column found in CSV'}), 400
            
            # Filter by location (case insensitive)
            if location:
                filtered_df = df[df[location_column].astype(str).str.lower().str.contains(location.lower(), na=False)]
            else:
                filtered_df = df.copy()
            
            # Group by location
            location_counts = filtered_df[location_column].value_counts().reset_index()
            location_counts.columns = ['label', 'value']
            
            # Limit to top 10 for better visualization
            if len(location_counts) > 10:
                location_counts = location_counts.head(10)
            
            result = {
                'labels': location_counts['label'].tolist(),
                'values': location_counts['value'].tolist(),
                'title': f'Patients by Location{f" - {location}" if location else ""}',
                'total_patients': len(filtered_df)
            }
            
        elif query_type == 'patients_by_treatment':
            # Query: How many patients had specific treatments?
            treatment = query_params.get('treatment', '')
            
            # Find treatment column
            treatment_column = None
            for col in ['treatment', 'description', 'procedure', 'service']:
                if col in df.columns:
                    treatment_column = col
                    break
            
            if not treatment_column:
                return jsonify({'error': 'No treatment column found in CSV'}), 400
            
            # Filter by treatment (case insensitive)
            if treatment:
                filtered_df = df[df[treatment_column].astype(str).str.lower().str.contains(treatment.lower(), na=False)]
            else:
                filtered_df = df.copy()
            
            # Group by treatment
            treatment_counts = filtered_df[treatment_column].value_counts().reset_index()
            treatment_counts.columns = ['label', 'value']
            
            # Limit to top 10 for better visualization
            if len(treatment_counts) > 10:
                treatment_counts = treatment_counts.head(10)
            
            result = {
                'labels': treatment_counts['label'].tolist(),
                'values': treatment_counts['value'].tolist(),
                'title': f'Patients by Treatment{f" - {treatment}" if treatment else ""}',
                'total_patients': len(filtered_df)
            }
            
        else:
            return jsonify({'error': 'Invalid query type'}), 400
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

# Add this route for finding a patient
@app.route('/find_patient', methods=['POST'])
def find_patient():
    try:
        data = request.json
        patient_id = data.get('patient_id', '').strip()
        patient_name = data.get('patient_name', '').strip()
        
        with data_lock:
            df = data_cache.copy() if data_cache is not None else None
        
        if df is None:
            return jsonify({'error': 'No data loaded. Please upload a CSV file first.'}), 400
        
        # Replace NaN values with None
        df = df.where(pd.notnull(df), None)
        
        # Try to find patient by ID or name
        patient = None
        
        # Find ID column (could be named 'id', 'patient_id', 'mrn', etc.)
        id_column = None
        for col in ['id', 'patient_id', 'mrn', 'patient_id']:
            if col in df.columns:
                id_column = col
                break
        
        # Find name column (could be named 'name', 'patient_name', etc.)
        name_column = None
        for col in ['name', 'patient_name', 'first_name', 'last_name']:
            if col in df.columns:
                name_column = col
                break
        
        # Search by ID if provided
        if patient_id and id_column:
            patient_df = df[df[id_column].astype(str).str.lower() == patient_id.lower()]
            if not patient_df.empty:
                patient = patient_df.iloc[0].to_dict()
        
        # Search by name if not found by ID
        if not patient and patient_name and name_column:
            patient_df = df[df[name_column].astype(str).str.lower().str.contains(patient_name.lower(), na=False)]
            if not patient_df.empty:
                patient = patient_df.iloc[0].to_dict()
        
        if patient:
            return jsonify({'patient': patient})
        else:
            return jsonify({'error': 'Patient not found'}), 404
    
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500
# === Entry Point ===
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
