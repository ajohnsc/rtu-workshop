import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import google.generativeai as genai

# --- Firebase Initialization ---
try:
    cred_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
    if cred_json:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase successfully initialized.")
    else:
        print("Error: FIREBASE_CREDENTIALS_JSON environment variable not found.")
        db = None
except Exception as e:
    print(f"Firebase initialization failed: {e}")
    db = None

# --- Gemini AI Initialization ---
try:
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        genai.configure(api_key=gemini_api_key)
        gemini_model = genai.GenerativeModel('gemini-2.5-flash')
        print("Gemini AI successfully initialized.")
    else:
        print("Error: GEMINI_API_KEY environment variable not found.")
        gemini_model = None
except Exception as e:
    print(f"Gemini AI initialization failed: {e}")
    gemini_model = None

# Configure Flask app
app = Flask(__name__, template_folder='../templates')
app.secret_key = 'super_secret_key_for_demo'

COLLECTION_NAME = 'vercel_flask_todos'

def format_timestamp(ts):
    if ts and hasattr(ts, 'seconds'):
        dt_object = ts.date()
        return dt_object.strftime("%b %d, %Y")
    return "N/A"

@app.route('/', methods=['GET', 'POST'])
def index():
    if db is None:
        return render_template('index.html', todos=[], db_error="Database not connected. Check environment variables.")
    
    if request.method == 'POST':
        task_content = request.form.get('content', '').strip()
        if task_content:
            try:
                doc_ref = db.collection(COLLECTION_NAME).add({
                    'content': task_content,
                    'completed': False,
                    'created_at': firestore.SERVER_TIMESTAMP
                })
                flash('Task added successfully!', 'success')
            except Exception as e:
                flash(f'Error adding task: {str(e)}', 'error')
        return redirect(url_for('index'))
    
    # GET request - show all todos
    try:
        todos_ref = db.collection(COLLECTION_NAME).order_by('created_at', direction=firestore.Query.DESCENDING)
        todos = []
        for doc in todos_ref.stream():
            todo_data = doc.to_dict()
            todo_data['id'] = doc.id
            todo_data['created_at_fmt'] = format_timestamp(todo_data.get('created_at'))
            todos.append(todo_data)
        return render_template('index.html', todos=todos)
    except Exception as e:
        return render_template('index.html', todos=[], db_error=f"Error fetching tasks: {str(e)}")

@app.route('/toggle/<task_id>')
def toggle_task(task_id):
    if db is None:
        flash('Database not available', 'error')
        return redirect(url_for('index'))
    
    try:
        doc_ref = db.collection(COLLECTION_NAME).document(task_id)
        doc = doc_ref.get()
        if doc.exists:
            current_status = doc.to_dict().get('completed', False)
            doc_ref.update({'completed': not current_status})
            flash('Task updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating task: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/delete/<task_id>')
def delete_task(task_id):
    if db is None:
        flash('Database not available', 'error')
        return redirect(url_for('index'))
    
    try:
        db.collection(COLLECTION_NAME).document(task_id).delete()
        flash('Task deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting task: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/suggest/<task_id>')
def get_suggestion(task_id):
    if db is None or gemini_model is None:
        return jsonify({'error': 'Database or Gemini AI not available'}), 500
    
    try:
        # Get the task from Firestore
        doc_ref = db.collection(COLLECTION_NAME).document(task_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return jsonify({'error': 'Task not found'}), 404
            
        task_content = doc.to_dict().get('content', '')
        
        # Generate suggestion using Gemini
        prompt = f"""
        I have a task: "{task_content}"
        
        Please provide a helpful suggestion or tip to accomplish this task more effectively. 
        Keep it concise, practical, and actionable. Respond in 1-2 sentences maximum.
        """
        
        response = gemini_model.generate_content(prompt)
        suggestion = response.text.strip()
        
        return jsonify({'suggestion': suggestion})
        
    except Exception as e:
        return jsonify({'error': f'Error generating suggestion: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)