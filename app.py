from flask import Flask, render_template, request, redirect, session, flash, url_for
import sqlite3
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import pickle
import random
import string
import os
import time
from twilio.rest import Client
import smtplib
from email.mime.text import MIMEText
from flask import send_file
from reportlab.pdfgen import canvas
import io

app = Flask(__name__)
app.secret_key = "secret123"

# Twilio OTP Setup
account_sid = "AC2a1cb44675b395a1327b3c396f90e93c"
auth_token = "5852640fde0975348806826c552be536"
service_sid = "VA8116c3ae1e03668d372003f1d1252d48"

client = Client(account_sid, auth_token)

# ---------------- DATABASE SETUP ----------------
def create_tables():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    
    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        name TEXT,
        username TEXT,
        password TEXT,
        mobile TEXT,
        email TEXT,
        location TEXT
    )
    """)
    
    # Function to add ID column if missing
    def migrate_table(table_name, schema):
        cur.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cur.fetchall()]
        if columns and 'id' not in columns:
            print(f"Migrating {table_name} to add ID column...")
            # 1. Rename old table
            cur.execute(f"ALTER TABLE {table_name} RENAME TO {table_name}_old")
            # 2. Create new table with ID
            cur.execute(schema)
            # 3. Copy data (excluding ID which will be auto-generated)
            col_string = ", ".join(columns)
            cur.execute(f"INSERT INTO {table_name} ({col_string}) SELECT {col_string} FROM {table_name}_old")
            # 4. Drop old table
            cur.execute(f"DROP TABLE {table_name}_old")
            conn.commit()

    # History table (Crop Prediction)
    crop_schema = """
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        temp REAL,
        humidity REAL,
        ph REAL,
        rainfall REAL,
        crop TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    cur.execute(crop_schema)
    migrate_table("history", crop_schema)

    # Soil Safety History
    soil_schema = """
    CREATE TABLE IF NOT EXISTS soil_safety_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        ph REAL,
        n REAL,
        p REAL,
        k REAL,
        result TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    cur.execute(soil_schema)
    migrate_table("soil_safety_history", soil_schema)

    # Disease Detection History
    disease_schema = """
    CREATE TABLE IF NOT EXISTS disease_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        image_path TEXT,
        result TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    cur.execute(disease_schema)
    migrate_table("disease_history", disease_schema)


    
    conn.commit()
    conn.close()

create_tables()

# ---------------- MODELS SETUP ----------------
# Load Crop Recommendation Model
crop_model = None
try:
    data = pd.read_excel("Crop_Recommendation_Dataset.xlsx")
    X = data.drop("Label", axis=1)
    y = data["Label"]
    crop_model = RandomForestClassifier(n_estimators=100)
    crop_model.fit(X, y)
    print("✅ Crop Recommendation Model Trained")
except Exception as e:
    print(f"❌ Error loading crop dataset: {e}")




# ---------------- HOME ----------------
@app.route('/')
def home():
    if 'username' in session:
        return redirect('/dashboard')
    return render_template('home.html')


# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    if request.method == 'POST':

        name = request.form['name']
        username = request.form['username']
        password = request.form['password']
        mobile = request.form['mobile']
        user_captcha = request.form.get('captcha_input')

        if user_captcha != session.get('captcha'):
            flash("Invalid Captcha ❌")
            conn.close()
            return redirect('/register')

        if not mobile.isdigit() or len(mobile) != 10:
            flash("Invalid Mobile Number ❌")
            conn.close()
            return redirect('/register')

        # Check username
        cur.execute("SELECT * FROM users WHERE username=?", (username,))
        if cur.fetchone():
            flash("Username already exists ❌")
            conn.close()
            return redirect('/register')

        # Check mobile
        cur.execute("SELECT * FROM users WHERE mobile=?", (mobile,))
        if cur.fetchone():
            flash("Mobile already registered ❌")
            conn.close()
            return redirect('/register')

        # Insert into database directly
        cur.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
            (
                name,
                username,
                password,
                mobile,
                "",
                ""
            )
        )
        conn.commit()
        conn.close()

        flash("Registered Successfully ✅")
        return redirect('/login')

    conn.close()

    # Generate captcha
    captcha = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    session['captcha'] = captcha
    return render_template("register.html", captcha=captcha)

# ---------------- DASHBOARD ----------------
@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect('/login')

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE username=?", (session['username'],))
    user = cur.fetchone()
    conn.close()

    import requests
    import datetime

    # Get current month name
    month_name = datetime.datetime.now().strftime("%B")
    
    # Define crops based on month
    crops_by_month = {
        "January": ["Wheat", "Mustard", "Gram", "Peas", "Potato", "Barley"],
        "February": ["Wheat", "Mustard", "Gram", "Peas", "Potato", "Barley"],
        "March": ["Moong", "Sunflower", "Watermelon", "Muskmelon", "Cucumber", "Maize"],
        "April": ["Moong", "Sunflower", "Watermelon", "Muskmelon", "Cucumber", "Maize"],
        "May": ["Rice", "Chili", "Tomato", "Brinjal", "Cucumber", "Okra"],
        "June": ["Rice", "Cotton", "Maize", "Soybean", "Groundnut", "Turmeric"],
        "July": ["Rice", "Cotton", "Maize", "Soybean", "Groundnut", "Turmeric"],
        "August": ["Rice", "Cotton", "Maize", "Soybean", "Groundnut", "Turmeric"],
        "September": ["Potato", "Onion", "Tomato", "Carrot", "Radish", "Peas"],
        "October": ["Wheat", "Mustard", "Gram", "Peas", "Potato", "Barley"],
        "November": ["Wheat", "Mustard", "Gram", "Peas", "Potato", "Barley"],
        "December": ["Wheat", "Mustard", "Gram", "Peas", "Potato", "Barley"]
    }
    
    current_month_crops = crops_by_month.get(month_name, ["Rice", "Maize", "Wheat", "Cotton", "Tomato", "Chili"])

    location = user[5]
    city = location.strip() if location and location.strip() else "Bangalore"

    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
    geo_data = requests.get(geo_url).json()

    if "results" in geo_data:
        latitude = geo_data["results"][0]["latitude"]
        longitude = geo_data["results"][0]["longitude"]
    else:
        latitude = 12.97
        longitude = 77.59
        city = location

    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m&daily=precipitation_probability_max&timezone=auto"

    data = requests.get(url).json()

    temp = data["current"]["temperature_2m"]
    humidity = data["current"]["relative_humidity_2m"]
    feels_like = data["current"]["apparent_temperature"]
    wind = data["current"]["wind_speed_10m"]
    rain = data["daily"]["precipitation_probability_max"][0]

    # FETCH RECENT HISTORY (Last 3)
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM history WHERE username=? ORDER BY date DESC LIMIT 3", (session['username'],))
    recent_crops = cur.fetchall()
    
    cur.execute("SELECT * FROM soil_safety_history WHERE username=? ORDER BY date DESC LIMIT 3", (session['username'],))
    recent_soil = cur.fetchall()
    

    
    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        city=city,
        temp=temp,
        humidity=humidity,
        feels_like=feels_like,
        wind=wind,
        rain=rain,
        recent_crops=recent_crops,
        recent_soil=recent_soil,
        month_name=month_name,
        current_month_crops=current_month_crops
    )
# ---------------- PREDICTION ----------------
@app.route('/predict', methods=['GET', 'POST'])
def predict():
    if 'username' not in session:
        return redirect('/login')

    if request.method == 'GET':
        return render_template('crop_prediction.html')

    print("🔥 Predict route working")

    try:
        temp = float(request.form['temp'])
        humidity = float(request.form['humidity'])
        ph = float(request.form['ph'])
        rainfall = float(request.form['rainfall'])
    except ValueError:
        flash("Invalid input. Please enter numbers.")
        return redirect('/dashboard')

    # Crop Prediction using our trained model
    if crop_model:
        prediction = crop_model.predict([[temp, humidity, ph, rainfall]])
        crop_name = prediction[0]
        session['crop_result'] = crop_name
        session['temp'] = temp
        session['humidity'] = humidity
    else:
        crop_name = "Model Error"
    fertilizer = "Urea"
    session['fertilizer_result'] = fertilizer
    # Soil Type
    if ph < 6:
        soil = "Sandy"
    elif ph > 7.5:
        soil = "Clay"
    else:
        soil = "Loamy"

    # Contamination
    if ph < 5 or ph > 8.5:
        contamination = "Polluted"
    else:
        contamination = "Safe"
    
    # Save to database
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    # Ensure table has date column (if it was created previously without it)
    cur.execute("PRAGMA table_info(history)")
    columns = [col[1] for col in cur.fetchall()]
    if 'date' not in columns:
        try:
            cur.execute("ALTER TABLE history ADD COLUMN date TIMESTAMP")
        except sqlite3.OperationalError:
            pass

    cur.execute("INSERT INTO history (username, temp, humidity, ph, rainfall, crop, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session['username'], temp, humidity, ph, rainfall, crop_name, time.strftime('%Y-%m-%d %H:%M:%S')))

    conn.commit()
    conn.close()

    return render_template("result.html",
                       crop=crop_name,
                       soil=soil,
                       contamination=contamination,
                       temp=temp,
                       humidity=humidity,
                       ph=ph,
                       rainfall=rainfall)


# ---------------- HISTORY ----------------
@app.route('/history')
def history():
    if 'username' not in session:
        return redirect('/login')

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    # Crop History
    cur.execute("SELECT * FROM history WHERE username=? ORDER BY date DESC", (session['username'],))
    crop_history = cur.fetchall()

    # Soil Safety History
    cur.execute("SELECT * FROM soil_safety_history WHERE username=? ORDER BY date DESC", (session['username'],))
    soil_history = cur.fetchall()
    
    # Disease Detection History
    cur.execute("SELECT * FROM disease_history WHERE username=? ORDER BY date DESC", (session['username'],))
    disease_history = cur.fetchall()

    conn.close()

    return render_template("history.html", 
                       crop_history=crop_history, 
                       soil_history=soil_history,
                       disease_history=disease_history)

# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully! ✅")
    return redirect('/')

# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form.get('username')
        password = request.form.get('password')
        user_captcha = request.form.get('captcha_input')

        if user_captcha != session.get('captcha'):
            flash("Invalid Captcha ❌")
            return redirect('/login')

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        )

        user = cur.fetchone()
        conn.close()

        if user:
            session['username'] = username
            flash("Login Successful ✅")
            return redirect('/dashboard')
        else:
            flash("Invalid Username or Password ❌")
            return redirect('/login')

    captcha = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    session['captcha'] = captcha

    return render_template("login.html", captcha=captcha)

# ---------------- FORGOT PASSWORD ----------------
@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        username = request.form.get('username')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cur.fetchone()

        if not user:
            conn.close()
            flash("User not found ❌")
            return redirect('/forgot')

        if new_password != confirm_password:
            conn.close()
            flash("Passwords do not match ❌")
            return redirect('/forgot')

        # Update password directly
        cur.execute("UPDATE users SET password=? WHERE username=?",
                    (new_password, username))
        conn.commit()
        conn.close()

        flash("Password Reset Successful ✅")
        return redirect('/login')

    return render_template("forgot.html")

# ---------------- USER PROFILE ----------------
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'username' not in session:
        return redirect('/login')

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    if request.method == 'POST':
        email = request.form['email']
        location = request.form['location']

        cur.execute("""
        UPDATE users SET email=?, location=?
        WHERE username=?
        """, (email, location, session['username']))

        conn.commit()

    # FETCH USER DATA
    cur.execute("SELECT * FROM users WHERE username=?", (session['username'],))
    user = cur.fetchone()

    conn.close()

    if not user:
        flash("User session expired. Please login again.")
        session.pop('username', None)
        return redirect('/login')

    return render_template("profile.html", user=user)

#---------------- SOIL SAFETY ----------------
@app.route('/soil_safety', methods=['GET', 'POST'])
def soil_safety():
    if 'username' not in session:
        return redirect('/login')

    result = None

    if request.method == 'POST':
        ph = float(request.form['ph'])
        n = float(request.form['nitrogen'])
        p = float(request.form['phosphorus'])
        k = float(request.form['potassium'])

        if ph < 5.5 or ph > 8.5:
            result = "❌ Soil is Contaminated"
        elif n < 20 or p < 20 or k < 20:
            result = "⚠️ Soil is Moderate"
        else:
            result = "✅ Soil is Safe"

        # SAVE TO HISTORY
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("INSERT INTO soil_safety_history (username, ph, n, p, k, result) VALUES (?, ?, ?, ?, ?, ?)",
                    (session['username'], ph, n, p, k, result))
        conn.commit()
        conn.close()

    return render_template('soil_safety.html', result=result)

#---------------- DISEASE DETECTION ----------------
@app.route('/disease', methods=['GET', 'POST'])
def disease_detection():
    if 'username' not in session:
        return redirect('/login')

    result = None
    image_path = None

    if request.method == 'POST':
        if 'plant_image' in request.files:
            file = request.files['plant_image']
            if file.filename != '':
                # Create static/uploads directory if it doesn't exist
                import os
                upload_folder = os.path.join('static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                
                # Save file
                import time
                filename = f"{session['username']}_{int(time.time())}_{file.filename}"
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                image_path = f"/static/uploads/{filename}"

                # Demo disease detection (mock result
                import random
                diseases = [
                    "🌿 Healthy Plant",
                    "🍃 Early Blight",
                    "🍂 Late Blight",
                    "🌾 Powdery Mildew",
                    "🪲 Bacterial Spot"
                ]
                result = random.choice(diseases)

                # Save to database
                conn = sqlite3.connect("database.db")
                cur = conn.cursor()
                cur.execute("INSERT INTO disease_history (username, image_path, result) VALUES (?, ?, ?)",
                            (session['username'], image_path, result))
                conn.commit()
                conn.close()

    return render_template('disease_detection.html', result=result)

# ---------------- SEND MESSAGE ----------------
# Contact Form Send Message
@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        # Get form data
        name = request.form['name']
        email = request.form['email']
        mobile = request.form['mobile']
        message = request.form['message']

        # Gmail Credentials
        sender_email = "surajshet290@gmail.com"
        sender_password = "wlxmvwfbekzpuuzf"

        # Receive Message Here
        receiver_email = "surajshet290@gmail.com"

        subject = "📩 New AgroXpert Contact Message"

        body = f"""
New Message from AgroXpert Website

Name: {name}
Email: {email}
Mobile: {mobile}

Message:
{message}
"""

        # Email Setup
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = receiver_email

        # SMTP
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()

        flash("Message Sent Successfully ✅")
        return redirect('/')

    except Exception as e:
        print("Error:", e)
        flash("Failed to Send Message ❌")
        return redirect('/')

# ---------------- PDF Report ----------------
@app.route('/download_crop_report')
def download_crop_report():
    if 'username' not in session:
        return redirect('/login')

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)
    
    # Page setup
    width, height = 595.27, 841.89  # A4 size
    
    # Title
    p.setFont("Helvetica-Bold", 24)
    p.setFillColorRGB(0.18, 0.49, 0.2)  # Dark green color
    p.drawString(180, 780, "AgroXpert Crop Report")
    
    # Header line
    p.setStrokeColorRGB(0.18, 0.49, 0.2)
    p.line(50, 765, 545, 765)
    
    # Content
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, 730, "User Details:")
    
    p.setFont("Helvetica", 12)
    p.drawString(70, 710, f"Username: {session.get('username', 'N/A')}")
    p.drawString(70, 690, f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, 650, "Analysis Results:")
    
    # Get values from session
    crop = session.get('crop_result', 'N/A')
    temp = session.get('temp', 'N/A')
    humidity = session.get('humidity', 'N/A')
    fertilizer = session.get('fertilizer_result', 'N/A')
    
    p.setFont("Helvetica", 12)
    p.drawString(70, 630, f"Predicted Crop: {crop}")
    p.drawString(70, 610, f"Recommended Fertilizer: {fertilizer}")
    p.drawString(70, 590, f"Temperature: {temp} °C")
    p.drawString(70, 570, f"Humidity: {humidity}%")
    
    # Disclaimer
    p.setFont("Helvetica-Oblique", 10)
    p.setFillColorRGB(0.5, 0.5, 0.5)
    p.drawString(50, 100, "Disclaimer: This report is generated by an AI model and should be used as a general guide.")
    p.drawString(50, 85, "Consult with an agricultural expert for precise recommendations.")
    
    # Footer
    p.setFillColorRGB(0.18, 0.49, 0.2)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(220, 50, "Sustainable Farming Companion")
    
    p.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"AgroXpert_Report_{session['username']}.pdf",
        mimetype='application/pdf'
    )
    mimetype='application/pdf'
    
#--------------Delete Crop History-----------------------
@app.route('/delete_crop/<int:id>')
def delete_crop(id):
    if 'username' not in session:
        return redirect('/login')

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("DELETE FROM history WHERE id=? AND username=?", (id, session['username']))

    conn.commit()
    conn.close()

    flash("Deleted successfully ✅")
    return redirect('/history')


@app.route('/delete_soil/<int:id>')
def delete_soil(id):
    if 'username' not in session:
        return redirect('/login')

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("DELETE FROM soil_safety_history WHERE id=? AND username=?", (id, session['username']))

    conn.commit()
    conn.close()

    flash("Soil history deleted ✅")
    return redirect('/history')

@app.route('/delete_disease/<int:id>')
def delete_disease(id):
    if 'username' not in session:
        return redirect('/login')

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("DELETE FROM disease_history WHERE id=? AND username=?", (id, session['username']))

    conn.commit()
    conn.close()

    flash("Disease detection history deleted ✅")
    return redirect('/history')


@app.route('/download_history_report/<int:history_id>')
def download_history_report(history_id):
    if 'username' not in session:
        return redirect('/login')

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM history WHERE id=? AND username=?", (history_id, session['username']))
    record = cur.fetchone()
    conn.close()

    if not record:
        flash("Record not found! ❌")
        return redirect('/history')

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)
    
    # Page setup
    width, height = 595.27, 841.89
    
    # Title
    p.setFont("Helvetica-Bold", 24)
    p.setFillColorRGB(0.18, 0.49, 0.2)
    p.drawString(180, 780, "AgroXpert Crop Report")
    
    p.setStrokeColorRGB(0.18, 0.49, 0.2)
    p.line(50, 765, 545, 765)
    
    # Content
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, 730, "User Details:")
    
    p.setFont("Helvetica", 12)
    p.drawString(70, 710, f"Username: {session['username']}")
    p.drawString(70, 690, f"Report Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    p.drawString(70, 670, f"Analysis Date: {record[7]}")
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, 630, "Analysis Results:")
    
    p.setFont("Helvetica", 12)
    p.drawString(70, 610, f"Predicted Crop: {record[6]}")
    p.drawString(70, 590, f"Temperature: {record[2]} °C")
    p.drawString(70, 570, f"Humidity: {record[3]}%")
    p.drawString(70, 550, f"pH Level: {record[4]}")
    p.drawString(70, 530, f"Rainfall: {record[5]} mm")
    
    # Disclaimer
    p.setFont("Helvetica-Oblique", 10)
    p.setFillColorRGB(0.5, 0.5, 0.5)
    p.drawString(50, 100, "Disclaimer: This report is generated by an AI model and should be used as a general guide.")
    p.drawString(50, 85, "Consult with an agricultural expert for precise recommendations.")
    
    # Footer
    p.setFillColorRGB(0.18, 0.49, 0.2)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(220, 50, "Sustainable Farming Companion")
    
    p.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"AgroXpert_Report_{record[0]}.pdf",
        mimetype='application/pdf'
    )


@app.route('/delete_all_history')
def delete_all_history():
    if 'username' not in session:
        return redirect('/login')

    username = session['username']
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    try:
        # Delete from all history tables
        cur.execute("DELETE FROM history WHERE username=?", (username,))
        cur.execute("DELETE FROM soil_safety_history WHERE username=?", (username,))
        cur.execute("DELETE FROM disease_history WHERE username=?", (username,))
        
        conn.commit()
        flash("All history cleared successfully! 🗑️")
    except Exception as e:
        conn.rollback()
        flash(f"Error clearing history: {str(e)} ❌")
    finally:
        conn.close()

    return redirect('/history')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)