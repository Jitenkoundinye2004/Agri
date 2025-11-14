import os
from flask import Flask, request, jsonify, render_template, url_for, session, redirect, send_from_directory
import requests
from datetime import datetime, timedelta
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_cors import CORS

app = Flask(__name__)

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.secret_key = 'your_super_secret_key_for_sessions' # Replace with a real secret key
OPENWEATHER_API_KEY = "1864f6678b009d19ea41eb2756dcfa92" # <-- IMPORTANT: Replace with your actual key

# Allow cross-origin requests for development (from your file:// or live server)
CORS(app)

# Replace with your MongoDB connection string.
# For local MongoDB, it's usually "mongodb://localhost:27017/your_db_name"
app.config["MONGO_URI"] = "mongodb://localhost:27017/agricare"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
mongo = PyMongo(app)

# --- Routes ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    user = None
    if 'user_email' in session:
        user = mongo.db.users.find_one({"email": session['user_email']})
    return render_template('index.html', user=user)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/register', methods=['POST'])
def register():
    """Handles user registration."""
    # Check if the post request has the file part
    if 'profile_photo' not in request.files:
        return jsonify({"message": "No profile photo part"}), 400
    
    photo = request.files['profile_photo']
    fullname = request.form.get('fullname')
    email = request.form.get('email')
    password = request.form.get('password')
    
    if photo.filename == '':
        return jsonify({"message": "No selected file"}), 400

    if not fullname or not email or not password:
        return jsonify({"message": "Missing required fields"}), 400

    # Check if user already exists
    if mongo.db.users.find_one({"email": email}):
        return jsonify({"message": "User with this email already exists"}), 409

    photo_path = None
    if photo and allowed_file(photo.filename):
        filename = secure_filename(photo.filename)
        # Create uploads directory if it doesn't exist
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        
        photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        # Store only the filename in the database, not the full path
        photo_path = filename
    else:
        return jsonify({"message": "Invalid file type"}), 400

    # Insert new user into the database
    hashed_password = generate_password_hash(password)
    mongo.db.users.insert_one({
        "fullname": fullname,
        "email": email,
        "password": hashed_password,
        "profile_photo_path": photo_path
    })

    # Automatically log the user in by setting the session
    session['user_email'] = email

    return jsonify({"message": "User registered successfully!"}), 201

@app.route('/login', methods=['POST'])
def login():
    """Handles user login."""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    user = mongo.db.users.find_one({"email": email})

    # Check if user exists and password is correct
    if user and check_password_hash(user['password'], password):
        # Store user's email in session to mark them as logged in
        session['user_email'] = user['email']
        return jsonify({"message": "Login successful!", "user": {"fullname": user['fullname']}}), 200
    else:
        return jsonify({"message": "Invalid email or password"}), 401

@app.route('/prediction', methods=['GET', 'POST'])
def prediction():
    # Check if user is logged in
    if 'user_email' not in session:
        return redirect(url_for('index')) # Redirect to home/login if not logged in

    user_email = session['user_email']
    user = mongo.db.users.find_one({"email": user_email})

    if not user:
        # If user somehow doesn't exist in DB, clear session and redirect
        session.pop('user_email', None)
        return redirect(url_for('index'))

    if request.method == 'POST':
        # --- Handle form submission for crop prediction ---
        season = request.form.get('season')
        crop_variety = request.form.get('crop_variety')
        soil_type = request.form.get('soil_type')
        state = request.form.get('state')
        district = request.form.get('district')
        taluka = request.form.get('taluka')
        village = request.form.get('village')  # Optional
        farm_area = request.form.get('farm_area')

        # Basic validation
        required_fields = [season, crop_variety, soil_type, state, district, taluka, farm_area]
        if not all(required_fields):
            # In a real app, you'd likely flash a message and re-render the form
            return jsonify({"message": "Missing required prediction fields"}), 400

        # --- Placeholder for your prediction model logic ---
        # You would typically pass these variables to your machine learning model
        # and get a prediction result.
        # For now, we'll just return a success message with the data.
        prediction_result = "Placeholder: High-Yield Wheat" # Example result

        return render_template('prediction.html', user=user, prediction_made=True, prediction_result=prediction_result)

    return render_template('prediction.html', user=user, prediction_made=False)

@app.route('/weather-forecast')
def weather_forecast():
    """
    Fetches real-time weather forecast data from Open-Meteo, using OpenWeatherMap for geocoding.
    This is for the original frontend which uses a GET request.
    """
    location = request.args.get('location')
    if not location:
        return jsonify({"message": "Location parameter is required"}), 400

    if not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY == "YOUR_OPENWEATHERMAP_API_KEY":
        return jsonify({"message": "OpenWeatherMap API key is not configured on the server."}), 500

    try:
        # 1. Geocoding: Convert location name to coordinates
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={OPENWEATHER_API_KEY}"
        geo_res = requests.get(geo_url)
        geo_res.raise_for_status()
        geo_data = geo_res.json()
        if not geo_data:
            return jsonify({"message": f"Could not find location: {location}"}), 404

        lat = geo_data[0]['lat']
        lon = geo_data[0]['lon']
        found_location_name = f"{geo_data[0]['name']}, {geo_data[0].get('state', '')}, {geo_data[0]['country']}"

        # 2. Open-Meteo API: Get current, hourly, and daily forecast. No API key needed for this part.
        forecast_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,precipitation_probability,wind_speed_10m"
            "&hourly=temperature_2m"
            "&daily=temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean"
            "&wind_speed_unit=kmh&timezone=auto"
        )
        meteo_res = requests.get(forecast_url)
        meteo_res.raise_for_status()
        meteo_data = meteo_res.json()

        # 3. Process data into the format the original frontend expects
        daily_forecast = [
            {
                "date": meteo_data['daily']['time'][i],
                "day_name": datetime.strptime(meteo_data['daily']['time'][i], "%Y-%m-%d").strftime("%a"),
                "max_temp": round(meteo_data['daily']['temperature_2m_max'][i]),
                "min_temp": round(meteo_data['daily']['temperature_2m_min'][i]),
                "humidity": round(meteo_data['daily']['relative_humidity_2m_mean'][i]),
            } for i in range(7)
        ]

        hourly_forecast = []
        for i in range(24):
            hourly_forecast.append({
                "hour": datetime.strptime(meteo_data['hourly']['time'][i], "%Y-%m-%dT%H:%M").strftime("%H:00"),
                "temp": round(meteo_data['hourly']['temperature_2m'][i]),
            })

        response_data = {
            "location": found_location_name,
            "current": {
                "temp": round(meteo_data['current']['temperature_2m']),
                "humidity": meteo_data['current']['relative_humidity_2m'],
                "precipitation": meteo_data['current']['precipitation_probability'], # Already a percentage
                "wind": round(meteo_data['current']['wind_speed_10m'], 1) # Already in km/h
            },
            "daily": daily_forecast,
            "hourly": hourly_forecast,
            "tips": [
                "Adjust irrigation if heavy rain is forecast.",
                "Avoid pesticide spraying before rain.",
                "Plan harvest on dry days for optimal quality."
            ]
        }
        return jsonify(response_data)

    except requests.exceptions.RequestException as e:
        return jsonify({"message": f"Failed to fetch weather data: {e}"}), 503
    except (KeyError, IndexError) as e:
        return jsonify({"message": f"Error processing weather data: {e}"}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/logout')
def logout():
    session.pop('user_email', None) # Clear the session
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)