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

os.environ['MONGO_URI'] = "mongodb://localhost:27017/nexus"

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24) # For session management
# Assuming `app` is your Flask app
CORS(app)

# MongoDB setup
client = MongoClient(os.getenv('MONGO_URI'))
db = client['nexus']
users_col = db['users']
components_col = db['components']

experiments_components = {
        '1': ["http://tinyurl.com/4vsnnsdh",'LED Bulb Project','Arduino Uno', 'LEDs', 'Jumper Wires', 'Microcontroller Board'],
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

model = load_model('D:/Nexus/app/keras_model.h5')  # Load your Keras model

@app.route('/detect', methods=['POST'])
def detect():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    img = Image.open(file.stream).resize((224, 224))  # Adjust size as per model requirement
    img_array = np.array(img) / 255.0  # Normalize image
    img_array = img_array.reshape((1, 224, 224, 3))  # Adjust shape as per model requirement
    
    class_names = open("app/labels.txt", "r").readlines()

    # Process predictions...
    # Assuming 'predictions' is the output of model.predict()
    predictions = model.predict(img_array)
    index = np.argmax(predictions)
    class_name = class_names[index].strip()  # Remove newline characters
    confidence_score = np.max(predictions)

    # Format the response to send back to the client
    response = {
        'class_name': class_name,
        'confidence_score': f"{confidence_score * 100:.2f}%"
    }

    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=True)