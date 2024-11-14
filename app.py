from flask import Flask, render_template, request, redirect, url_for
import os
import time
from PIL import Image
import google.generativeai as genai
import re

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
processed_images = set()

# Initialize the Gemini API client
genai.configure(api_key="AIzaSyB_RFI7WlcUZJLC1eVGjrjZyUH_wX74RVo")  # Replace with your actual API key
model = genai.GenerativeModel("gemini-1.5-flash")

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_next_image_number():
    # Regular expression to match files in the format captured_image_<number>.png
    pattern = r'captured_image_(\d+)\.png'
    numbers = []

    for f in os.listdir(app.config['UPLOAD_FOLDER']):
        # Check if the filename matches the pattern
        match = re.match(pattern, f)
        if match:
            # Extract the number from the matched filename
            number = int(match.group(1))
            numbers.append(number)

    return max(numbers) + 1 if numbers else 1

@app.route('/')
def index():
    return render_template('index.html', processed_message='Waiting for image capture...')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No file part"
    
    file = request.files['file']
    if file.filename == '':
        return "No selected file"
    
    if file:
        # Check if the file is a PNG image
        if not file.filename.lower().endswith('.png'):
            return "Only PNG images are allowed"
        
        # Generate a unique filename based on the next available number
        image_number = get_next_image_number()
        filename = f'captured_image_{image_number}.png'
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(file_path)
            return "Image uploaded successfully"
        except Exception as e:
            return f"Error saving file: {e}"


def process_new_images():
    while True:
        uploaded_images = set(os.listdir(app.config['UPLOAD_FOLDER']))
        new_images = uploaded_images - processed_images

        for img_name in new_images:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], img_name)
            print(f"Processing {img_name}...")

            # Open the new image
            image = Image.open(img_path)

            # Send to Gemini API with the prompt
            response = model.generate_content(["Reply in one word, is this bio degradable or non-biodegradable", image])
            print("Gemini API Response:", response.text)  # Print Gemini's response

            processed_images.add(img_name)
            print(f"Processed {img_name}")

        time.sleep(2)  # Poll every 2 seconds

if __name__ == "__main__":
    from threading import Thread
    process_thread = Thread(target=process_new_images)
    process_thread.start()
    app.run(debug=True)
