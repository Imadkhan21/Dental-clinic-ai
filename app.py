import os
import shutil
import pandas as pd
import sqlite3
import threading
import re
import io
import base64
import json
import matplotlib.pyplot as plt
import uuid
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from chatbot_model import get_chat_response  # Make sure chatbot_model.py exists
from bs4 import BeautifulSoup
import traceback
import time

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
app.secret_key = 'AIzaSyDhSrwZaIdEM2WVIELNAu7qIa-WRfbsqn4'

# === DB Initialization ===
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                        (id INTEGER PRIMARY KEY, message TEXT, response TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS current_file 
                        (id INTEGER PRIMARY KEY, filename TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS content_links 
                        (id TEXT PRIMARY KEY, content_type TEXT, content_data TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
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

# === Helper function to parse HTML table to JSON ===
def parse_table_to_json(html_content):
    """Parse HTML table to structured JSON data"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        table = soup.find('table')
        
        if not table:
            return None
            
        # Extract headers
        headers = []
        header_row = table.find('tr')
        if header_row:
            for th in header_row.find_all(['th', 'td']):
                headers.append(th.get_text(strip=True))
        
        # Extract rows
        rows = []
        for row in table.find_all('tr')[1:]:  # Skip header row
            cells = []
            for cell in row.find_all(['td', 'th']):
                cells.append(cell.get_text(strip=True))
            if cells:
                rows.append(cells)
        
        return {
            "headers": headers,
            "rows": rows
        }
    except Exception as e:
        print(f"[ERROR] Error parsing table: {str(e)}")
        return None

# === Helper function to generate table HTML ===
def generate_table_html(headers, rows):
    """Generate HTML table from headers and rows"""
    html = "<table border='1' style='border-collapse: collapse; width: 100%;'>\n"
    
    # Add headers
    html += "<tr style='background-color: #f2f2f2;'>\n"
    for header in headers:
        html += f"<th style='padding: 8px; text-align: left;'>{header}</th>\n"
    html += "</tr>\n"
    
    # Add rows
    for i, row in enumerate(rows):
        bg_color = "#f9f9f9" if i % 2 == 0 else "white"
        html += f"<tr style='background-color: {bg_color};'>\n"
        for cell in row:
            html += f"<td style='padding: 8px;'>{cell}</td>\n"
        html += "</tr>\n"
    
    html += "</table>"
    return html

# === Helper function to generate chart HTML ===
def generate_chart_html(chart_data):
    """Generate HTML for chart from chart data"""
    try:
        labels = chart_data.get("labels", [])
        values = chart_data.get("values", [])
        title = chart_data.get("title", "Chart")
        
        # Generate chart
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(labels, values)
        ax.set_title(title)
        ax.set_xlabel("Category")
        ax.set_ylabel("Value")
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # Convert to base64
        img = io.BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        plot_url = base64.b64encode(img.getvalue()).decode()
        plt.close(fig)
        
        # Create HTML
        html = f"""
        <div style="text-align: center; margin: 20px;">
            <h2>{title}</h2>
            <img src="data:image/png;base64,{plot_url}" alt="{title}" style="max-width: 100%; height: auto;">
        </div>
        """
        return html
    except Exception as e:
        print(f"[ERROR] Error generating chart HTML: {str(e)}")
        return f"<p>Error generating chart: {str(e)}</p>"

# === Helper function to convert table to text list ===
def table_to_text_list(html_content):
    """Convert HTML table to text list format"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        table = soup.find('table')
        
        if not table:
            return html_content
            
        # Extract headers
        headers = []
        header_row = table.find('tr')
        if header_row:
            for th in header_row.find_all(['th', 'td']):
                headers.append(th.get_text(strip=True))
        
        # Extract rows
        rows = []
        for row in table.find_all('tr')[1:]:  # Skip header row
            cells = []
            for cell in row.find_all(['td', 'th']):
                cells.append(cell.get_text(strip=True))
            if cells:
                rows.append(cells)
        
        # Convert to text list format
        text_list = ""
        for i, row in enumerate(rows):
            text_list += f"{i+1}. "
            for j, cell in enumerate(row):
                if j < len(headers):
                    text_list += f"{headers[j]}: {cell}"
                else:
                    text_list += f"{cell}"
                if j < len(row) - 1:
                    text_list += ", "
            text_list += "\n"
        
        return text_list
    except Exception as e:
        print(f"[ERROR] Error converting table to text list: {str(e)}")
        return html_content

# === Helper function to check if user is asking for a list ===
def is_asking_for_list(user_input):
    """Check if the user is asking for a list format"""
    list_keywords = ['list', 'listing', 'show me list', 'give me list', 'in list format', 'as a list']
    user_input_lower = user_input.lower()
    
    for keyword in list_keywords:
        if keyword in user_input_lower:
            return True
    
    return False

# === Routes ===
@app.route('/')
def index():
    current_file = get_current_file()
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message, response FROM chat_history")
        history = cursor.fetchall()
    return render_template('index.html', history=history, filename=current_file)

@app.route('/view/<content_id>')
def view_content(content_id):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content_type, content_data FROM content_links WHERE id = ?", (content_id,))
            result = cursor.fetchone()
        
        if not result:
            return "Content not found", 404
            
        content_type, content_data = result
        content_data = json.loads(content_data)
        
        if content_type == "table":
            headers = content_data.get("headers", [])
            rows = content_data.get("rows", [])
            table_html = generate_table_html(headers, rows)
            
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Data Table</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1 {{ color: #333; }}
                </style>
            </head>
            <body>
                <h1>Data Table</h1>
                {table_html}
            </body>
            </html>
            """
            
        elif content_type == "chart":
            chart_html = generate_chart_html(content_data)
            
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Chart</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1 {{ color: #333; }}
                </style>
            </head>
            <body>
                <h1>Chart</h1>
                {chart_html}
            </body>
            </html>
            """
        else:
            return "Invalid content type", 400
            
    except Exception as e:
        print(f"[ERROR] Error viewing content: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/ask', methods=['POST'])
def ask():
    global stop_execution_flag
    stop_execution_flag = False  # reset at the start of request
    start_time = time.time()
    
    try:
        user_input = request.json.get('message') if request.is_json else request.form.get('message')
        print(f"[DEBUG] Received request: {user_input}")
        
        with data_lock:
            df = data_cache
        
        if df is None:
            print("[DEBUG] No data loaded")
            return jsonify({
                'response': '⚠ No file uploaded or data loaded. Please upload a CSV first.',
                'template_url': ''
            })
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message, response FROM chat_history ORDER BY id ASC")
            session_history = cursor.fetchall()
        
        if stop_execution_flag:
            print("[DEBUG] Execution stopped by flag")
            return jsonify({'status': 'stopped', 'response': None, 'template_url': ''})
        
        print(f"[DEBUG] Getting chat response... (Time: {time.time() - start_time:.2f}s)")
        try:
            response = get_chat_response(user_input, df, session_history=session_history)
            print(f"[DEBUG] Got response in {time.time() - start_time:.2f}s")
            print(f"[DEBUG] Response length: {len(response)} characters")
            print(f"[DEBUG] Response preview: {response[:200]}...")
            
            # Check if response is empty
            if not response or response.strip() == "":
                print("[DEBUG] Empty response from get_chat_response")
                response = "I'm sorry, I couldn't generate a response. Please try a different question."
                
        except Exception as e:
            print(f"[ERROR] Error in get_chat_response: {str(e)}")
            print(traceback.format_exc())
            return jsonify({
                'response': f'Error getting response: {str(e)}',
                'template_url': ''
            })
        
        if stop_execution_flag:
            print("[DEBUG] Execution stopped by flag after getting response")
            return jsonify({'status': 'stopped', 'response': None, 'template_url': ''})
        
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO chat_history (message, response) VALUES (?, ?)", (user_input, response))
                conn.commit()
            print("[DEBUG] Saved to chat history")
        except Exception as e:
            print(f"[ERROR] Error saving to chat history: {str(e)}")
        
        # Check if the user is asking for a list and the response contains a table
        if is_asking_for_list(user_input) and "<table" in response:
            print("[DEBUG] User asked for a list and response contains a table, converting to text list")
            # Convert table to text list
            text_list = table_to_text_list(response)
            # Return the text list in the response field
            return jsonify({
                'response': text_list,
                'template_url': ''
            })
        
        # Check if the response contains a table and user is not asking for a list
        elif "<table" in response and not is_asking_for_list(user_input):
            print("[DEBUG] Response contains table and user didn't ask for a list")
            try:
                # Parse the HTML table to structured JSON
                structured_data = parse_table_to_json(response)
                if structured_data:
                    # Generate a unique ID for this content
                    content_id = str(uuid.uuid4())
                    
                    # Store the content in the database
                    with sqlite3.connect(DB_FILE) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO content_links (id, content_type, content_data) VALUES (?, ?, ?)",
                            (content_id, "table", json.dumps(structured_data))
                        )
                        conn.commit()
                    
                    # Generate the URL
                    content_url = url_for('view_content', content_id=content_id, _external=True)
                    print(f"[DEBUG] Generated table URL: {content_url}")
                    
                    # Return empty response and URL in template_url
                    return jsonify({
                        'response': '',
                        'template_url': content_url
                    })
                else:
                    print("[DEBUG] Failed to parse table, returning as text")
                    return jsonify({
                        'response': response,
                        'template_url': ''
                    })
            except Exception as e:
                print(f"[ERROR] Error creating table link: {str(e)}")
                print(traceback.format_exc())
                # Fall back to the original response
                return jsonify({
                    'response': response,
                    'template_url': ''
                })
        
        # Check if the response contains chart data
        elif "CHART_DATA:" in response:
            print("[DEBUG] Response contains chart data")
            try:
                # Extract the JSON part after "CHART_DATA:"
                chart_str = response.split("CHART_DATA:")[1].strip()
                print(f"[DEBUG] Extracted chart string: {chart_str[:100]}...")
                
                # Parse the JSON
                chart_json = json.loads(chart_str)
                print(f"[DEBUG] Parsed chart JSON: {chart_json}")
                
                # Generate a unique ID for this content
                content_id = str(uuid.uuid4())
                
                # Store the content in the database
                with sqlite3.connect(DB_FILE) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO content_links (id, content_type, content_data) VALUES (?, ?, ?)",
                        (content_id, "chart", json.dumps(chart_json))
                    )
                    conn.commit()
                
                # Generate the URL
                content_url = url_for('view_content', content_id=content_id, _external=True)
                print(f"[DEBUG] Generated chart URL: {content_url}")
                
                # Return empty response and URL in template_url
                return jsonify({
                    'response': '',
                    'template_url': content_url
                })
            except Exception as e:
                print(f"[ERROR] Error creating chart link: {str(e)}")
                print(traceback.format_exc())
                # Fall back to the original response
                return jsonify({
                    'response': response,
                    'template_url': ''
                })
        
        # Regular text response
        else:
            print("[DEBUG] Regular text response")
            # Return the text response in the response field and empty template_url
            return jsonify({
                'response': response,
                'template_url': ''
            })
    
    except Exception as e:
        print(f"[ERROR] Unhandled exception in /ask: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'response': f'Error: {str(e)}',
            'template_url': ''
        })
    
    finally:
        print(f"[DEBUG] Request completed in {time.time() - start_time:.2f}s")

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

# === Entry Point ===
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5003))
    app.run(host='0.0.0.0', port=port, debug=True)