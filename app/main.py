from flask import Flask, request, jsonify
import psycopg2
import os
from apscheduler.schedulers.background import BackgroundScheduler
import joblib
import re
from psycopg2.extras import RealDictCursor
import requests
from pytz import timezone
import datetime
from datetime import datetime, date

# Define the South Africa timezone
sa_timezone = timezone('Africa/Johannesburg')
 
# Global Flask app and Scheduler
app = Flask(__name__)
scheduler = BackgroundScheduler()

# Scheduler Setup
scheduler.configure(timezone=sa_timezone)

# Load ML Models
vectorizer = joblib.load('models/tfidf_vectorizer.pkl')
model = joblib.load('models/kmeans_model.pkl')

# Database Connection Function
def get_db_connection():
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        return conn
    except psycopg2.OperationalError as e:
        print("Database connection error:", e)
        return None
        
# Text Preprocessing Function
def preprocess_text(text):
    if isinstance(text, str):
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', '', text)
    else:
        text = ''
    return text
 
# Cluster Labels
cluster_labels = {
    0: "Rig and Tripping Issues",
    1: "Oil and Leak Issues",
    2: "Engine Starting Problems",
    3: "CAS and Equipment Issues",
    4: "Brake and Pressure Issues",
    5: "Overheating and Engine Problems",
    6: "Engine Cutting and Overheating",
    7: "Bucket Movement and Cylinder Issues",
    8: "Steering and Cylinder Faults",
    9: "Drilling and Spanner Issues",
    10: "Emulsion Pumping Problems",
    11: "Drifter and Bolt Issues",
    12: "Pump and Hydraulic Issues",
    13: "Movement and Gear Problems",
    14: "Brakes Binding and Overheating",
    15: "Hydraulic Pipe Leaks",
    16: "Chain and Actuator Breakages",
    17: "Feed Sling and Cylinder Damage",
    18: "Motor and Compressor Faults",
    19: "Spanner and Chain Malfunctions",
    20: "Hydraulic Pipe Bursts",
    21: "Reverse Movement and Power Issues",
    22: "Excessive Smoking Issues",
    23: "Engine and Remote Faults",
    24: "Boom Movement and Engine Issues",
    25: "Tramming and Power Issues",
    26: "Lighting and Rear Warning Issues",
    27: "Hydraulic Oil Leaks",
    28: "Power and Trimming Problems",
    29: "Power Pack and Tripping Issues",
    30: "Jack and Stabilizer Malfunctions",
    31: "Tyre and Sling Damage",
    32: "Steering and Turning Issues",
    33: "Profshaft and Bolt Problems",
    34: "Engine Cut and Sensor Faults",
    35: "Water Mixing and Leakage",
    36: "Alternator and Charging Issues"
}
 
# Classify and Update Function
def classify_and_update(text_data_list=None, ids=None, table_names=None):
    if not text_data_list or not ids or not table_names:
        data = request.json
        text_data_list = data.get('texts', [])
        ids = data.get('ids', [])
        table_names = data.get('table_names', [])

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        exclude_keywords = ['service', 'extended service']

        for i, text in enumerate(text_data_list):
            text_lower = text.lower()
            if any(keyword in text_lower for keyword in exclude_keywords):
                prediction = -1
                label = text
            else:
                tfidf_data = vectorizer.transform([preprocess_text(text)])
                prediction = int(model.predict(tfidf_data)[0])
                label = cluster_labels.get(prediction, "Others")

            update_query = f"""
                UPDATE {table_names[i]} SET
                processed_report = %s,
                predicted_cluster = %s,
                predicted_label = %s
                WHERE id = %s
            """
            cursor.execute(update_query, (text, prediction, label, ids[i]))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)})

# Reporting Procedure Function
def run_reporting_procedure():
    try:
        connection = psycopg2.connect(os.environ['DATABASE_URL'])
        cursor = connection.cursor()
        cursor.execute("SELECT run_reporting_procedures();")
        connection.commit()
        print("Reporting procedures executed successfully.")
    except Exception as e:
        print("An error occurred:", e)
    finally:
        if 'connection' in locals() and connection:
            cursor.close()
            connection.close()
            
# Classification for Date Function
@app.route('/run_classification_for_date', methods=['GET'])
def run_classification_for_date(start_date=None, end_date=None):
    conn = None
    try:
        start_time = datetime.now()
        if not start_date or not end_date:
            today_date = date.today().strftime('%Y-%m-%d')
            start_date = end_date = today_date

        conn = get_db_connection()
        if conn is None:
            raise Exception("Failed to connect to the database.")

        cursor = conn.cursor()
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'mo%_brk_cap_ai' AND table_schema='public'")
        tables = cursor.fetchall()
        batch_size = 100

        for table in tables:
            table_name = table['table_name']
            offset = 0

            while True:
                query = f"""
                    SELECT id, what_was_report_by_tm_3_operator 
                    FROM {table_name} 
                    WHERE date = %s
                    AND what_was_report_by_tm_3_operator IS NOT NULL 
                    AND TRIM(what_was_report_by_tm_3_operator) <> ''
                    LIMIT {batch_size} OFFSET {offset}
                """
                cursor.execute(query, (today_date,))
                batch_data = cursor.fetchall()

                if not batch_data:
                    break

                ids = [item['id'] for item in batch_data]
                texts = [item['what_was_report_by_tm_3_operator'] for item in batch_data]
                table_names = [table_name] * len(batch_data)

                # Direct function call
                classify_and_update(text_data_list=texts, ids=ids, table_names=table_names)

                offset += batch_size

        end_time = datetime.datetime.now()
        time_elapsed = end_time - start_time
        print(f"Classification completed. Time elapsed: {time_elapsed}")

        return jsonify({'status': 'Classification process completed', 'time_elapsed': str(time_elapsed)})
    except Exception as e:
        print("An error occurred:", e)
    finally:
        if conn is not None:
            conn.close()
          
# Scheduler Setup
scheduler.configure(timezone=sa_timezone)
scheduler.add_job(run_reporting_procedure, trigger="interval", minutes=60)
scheduler.add_job(lambda: run_classification_for_date(), 'cron', hour=6, minute=30)
scheduler.add_job(lambda: run_classification_for_date(), 'cron', hour=18, minute=30)
scheduler.start()
     
# Route Definitions
@app.route('/')
def index():
    return "The combined Flask app is running."

@app.route('/run-report')
def run_report():
    run_reporting_procedure()
    return "Report procedure initiated."
 
@app.route('/run_classification_custom_range', methods=['GET'])
def run_classification_custom_range():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    run_classification_for_date(start_date, end_date)
    return jsonify({'status': 'Custom range classification initiated'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int("8080"), debug=False) 
