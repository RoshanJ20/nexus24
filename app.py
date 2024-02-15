from flask import Flask, request, redirect, url_for, render_template, session, jsonify
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import numpy as np
from PIL import Image
from io import BytesIO
from keras.models import load_model


global experiments_components
global barcode

from flask_cors import CORS

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from keras.models import load_model
import numpy as np
from PIL import Image
import base64
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)


os.environ['MONGO_URI'] = "mongodb://localhost:27017/nexus"

load_dotenv()
CORS(app, methods=['GET', 'POST', 'PUT', 'DELETE'])

# MongoDB setup
client = MongoClient(os.getenv('MONGO_URI'))
db = client['nexus']
users_col = db['users']
components_col = db['components']
model = load_model('D:/nexus24/keras_model2.h5')
class_names = [line.strip() for line in open("D:/nexus24/labels2.txt", "r").readlines()]


experiments_components = {
        '1': ["http://tinyurl.com/4vsnnsdh",'LED Bulb Project','Ultrasonic Sensor', 'LEDs', 'Arduino UNO', 'Breadboard'],
        '2': ["http://tinyurl.com/4xnk6dea",'Soil Moisture Project', 'Soil Moisture Sensor', 'ESP8266', 'Jumper Wires' ],
        '3': ["http://tinyurl.com/2wpbd77c",'Ultrasonic Sensor Project' ,'Arduino Uno', 'HC-SR04 Ultrasonic Sensor', 'Jumper Wires', 'Breadboard'],
        '4': ["http://tinyurl.com/4vsnnsdh",'LED Bulb Project','Arduino Uno', 'LEDs', 'Jumper Wires', 'Microcontroller Board'],
        '5': ["http://tinyurl.com/4xnk6dea", 'Soil Moisture Project','Soil Moisture Sensor', 'ESP8266', 'Jumper Wires' ],
        # Add more experiments and their components here
    }


from flask import request, jsonify

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        data = request.get_json()
        register_number = data['register_number']
        session['register_number'] = register_number
        # You can now redirect or return a success response
        return jsonify({"status": "success", "register_number": register_number})
    return render_template('home.html')

@app.route('/experiments', methods=['GET', 'POST'])
def experiments():
    if request.method == 'GET':
        # Store barcode from query parameter in session on initial GET request
        barcode = request.args.get('barcode', default=None, type=str)
        print(barcode)
        if barcode:
            session['barcode'] = barcode

    if request.method == 'POST':
        exp_no = request.form['experiment']
        print(exp_no)
        session['experiment'] = exp_no
        barcode = session.get('barcode', None)  # Retrieve barcode from session
        # Assign experiment to register number (ensure 'register_number' is also managed correctly)
        users_col.update_one({'userno': session['barcode']}, {'$set': {'expno': exp_no}}, upsert=True)
        components = experiments_components.get(exp_no, [])
        return render_template('experiments.html', experiments=experiments_components, selected_experiment=exp_no, components=components, show_components=True, barcode=barcode)
    else:
        # On initial load, no experiment is selected
        barcode = session.get('barcode', None)
        return render_template('experiments.html', experiments=experiments_components, show_components=False, barcode=barcode)
    
@app.route('/save', methods=['POST'])
def save():
    exp_no = session.get('experiment')
    update_components(exp_no)
    session.clear() # End session
    return redirect(url_for('home'))

def update_components(exp_no):
    # Retrieve the list of components for the given experiment number
    required_components = experiments_components.get(exp_no, [])

    # Iterate through the required components and decrement their quantity in the database
    for component_name in required_components:
        components_col.update_one(
            {'name': component_name},
            {'$inc': {'quantity': -1}}  # Decrement the quantity by 1
        )


@app.route('/return', methods=['GET', 'POST'])
def return_exp():
    if request.method == 'POST':
        exp_no = request.form.get('exp_no')
        faulty_components = request.form.getlist('faultyComponents[]')
        barcode = session.get('barcode')  # Ensure barcode is correctly retrieved from the session

        # Process the returned components
        if exp_no:
            all_components = experiments_components[exp_no][2:]  # Assuming components start from index 2

            for component in all_components:
                if component in faulty_components:
                    # Insert faulty components into the fault table with userno and component name
                    db.fault.insert_one({'component_name': component})
                else:
                    # Increment the quantity of the non-faulty components in the components table
                    components_col.update_one({'name': component}, {'$inc': {'quantity': 1}})

            # Optionally: Update the user's record to remove or update the returned experiment number
            # Redirect to the home page after processing
            session.pop('barcode', None)  # Clear the barcode from the session to prevent reuse
            return redirect(url_for('home'))

    # Handle GET request to display the return form with experiments for the given user/barcode
    if request.method == 'GET':
        barcode = request.args.get('barcode', None)
        if not barcode:
            return "No barcode provided", 400

        user_record = users_col.find_one({"userno": barcode})
        if not user_record:
            return "User not found", 404

        borrowed_exps = user_record.get('expno', [])
        filtered_experiments = {k: experiments_components[k] for k in borrowed_exps if k in experiments_components}
        return render_template('return.html', experiments_components=filtered_experiments, barcode=barcode)

    return "Invalid request method.", 405

    
def increment_components(exp_no):
    required_components = experiments_components.get(exp_no, [])
    for component_name in required_components:
        components_col.update_one(
            {'name': component_name},
            {'$inc': {'quantity': 1}}  # Increment the quantity by 1
        )

@app.route('/detect')
def detect_page():
    return render_template('detect.html')

@socketio.on('image')
def handle_image(data):
    # Decode image
    img_data = data['image'].split(",")[1]
    img = Image.open(io.BytesIO(base64.b64decode(img_data))).convert('RGB')
    img = img.resize((224, 224))
    img_array = np.asarray(img) / 255.0
    img_array = np.expand_dims(img_array, axis=0)
    
    # Make prediction
    predictions = model.predict(img_array)
    max_index = np.argmax(predictions[0])
    predicted_class = class_names[max_index]
    confidence = float(predictions[0][max_index])
    
    # Emit the result back to the client
    emit('detection_result', {'class_name': predicted_class, 'confidence': confidence})

@app.route('/save_detected_components', methods=['POST'])
def save_detected_components():
    data = request.get_json()
    selected_components = data.get('components', [])
    
    if not selected_components:
        return jsonify({"error": "No components selected"}), 400

    for component_name in selected_components:
        # Assuming 'components_col' is your MongoDB collection for components
        # Update the component's quantity. Adjust the field names as per your database schema.
        components_col.update_one(
            {'name': component_name},
            {'$inc': {'quantity': 1}}
        )

    return jsonify({"message": "Components saved successfully"}), 200

@app.route('/components_list')
def components_list():
    # For simplicity, extracting component names from the experiments_components dictionary
    all_components = set()  # Use a set to avoid duplicate components
    for experiment in experiments_components.values():
        for component in experiment[2:]:  # Assuming component names start from index 2
            all_components.add(component)
        break
    return jsonify(list(all_components))

if __name__ == '__main__':
    socketio.run(app, debug=True)