from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
import time
from PIL import Image
import google.generativeai as genai
import re
import serial
from threading import Thread, Event
from queue import Queue, Empty
import logging
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ArduinoController:
    def __init__(self, port='COM7', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.arduino = None
        self.connect()

    def connect(self):
        try:
            self.arduino = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=1)
            logger.info(f"Connected to Arduino on {self.port}")
        except serial.SerialException as e:
            logger.error(f"Failed to connect to Arduino: {e}")
            self.arduino = None

    def send_command(self, command):
        if not self.arduino:
            logger.error("Arduino not connected")
            return False
        try:
            self.arduino.write(command.encode())
            return True
        except Exception as e:
            logger.error(f"Error sending command to Arduino: {e}")
            return False

    def close(self):
        if self.arduino:
            try:
                self.arduino.close()
                logger.info("Arduino connection closed")
            except Exception as e:
                logger.error(f"Error closing Arduino connection: {e}")

class ImageProcessor:
    def __init__(self):
        self.process_queue = Queue()
        self.stop_event = Event()
        self.processing_thread = None
        self.arduino = ArduinoController()
        self.initialize_gemini()
        
    def initialize_gemini(self):
        try:
            genai.configure(api_key="AIzaSyB_RFI7WlcUZJLC1eVGjrjZyUH_wX74RVo")
            self.model = genai.GenerativeModel("gemini-1.5-flash")
            logger.info("Gemini API initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini API: {e}")
            raise

    def start(self):
        if self.processing_thread and self.processing_thread.is_alive():
            logger.warning("Processing thread already running")
            return
        
        self.stop_event.clear()
        self.processing_thread = Thread(target=self._process_queue)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        logger.info("Processing thread started")

    def stop(self):
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info("Stopping processing thread...")
            self.stop_event.set()
            self.processing_thread.join(timeout=5)
            self.arduino.close()
            logger.info("Processing thread stopped")
        
    def _process_queue(self):
        logger.info("Processing thread is running")
        while not self.stop_event.is_set():
            try:
                img_path = self.process_queue.get(timeout=1)
                logger.info(f"Processing image from path: {img_path}")
                self._process_image(img_path)
                self.process_queue.task_done()
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in processing thread: {e}")
                time.sleep(1)

    def _process_image(self, img_path):
        if not os.path.exists(img_path):
            logger.error(f"Image file not found: {img_path}")
            return

        try:
            logger.info(f"Opening image: {img_path}")
            image = Image.open(img_path)
            
            logger.info("Sending image to Gemini API")
            response = self.model.generate_content([
                "Reply in one word, is this biodegradable or non-biodegradable",
                image
            ])
            
            gemini_response = response.text.strip().lower()
            logger.info(f"Gemini API Response: {gemini_response}")
            render_template('index.html', processed_message=gemini_response)
            
            if "biodegradable" in gemini_response:
                logger.info("Detected biodegradable waste")
                success = self.arduino.send_command('1')
            elif "non-biodegradable" in gemini_response:
                logger.info("Detected non-biodegradable waste")
                success = self.arduino.send_command('2')
            else:
                logger.warning(f"Unexpected response from Gemini: {gemini_response}")
                return
            
            if success:
                logger.info(f"Successfully processed {img_path}: {gemini_response}")
            else:
                logger.error(f"Failed to send command to Arduino for {img_path}")
            
        except Exception as e:
            logger.error(f"Error processing image {img_path}: {e}")
            logger.exception("Full traceback:")



# Create a single instance of the processor
processor = None

def get_processor():
    global processor
    if processor is None:
        processor = ImageProcessor()
        processor.start()
    return processor

@app.route('/')
def index():
    return render_template('index.html', processed_message='Waiting for image capture...')

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        logger.info(f"File saved to {filepath}")
        
        # Get the processor instance and queue the image
        processor = get_processor()
        processor.process_queue.put(filepath)
        logger.info(f"Image queued for processing: {filepath}")
        
        return jsonify({'message': 'Image queued for processing'})
    except Exception as e:
        logger.error(f"Error handling upload: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Don't stop the processor on every request
@app.teardown_appcontext
def cleanup(exception=None):
    pass

if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    # Initialize the processor before running the app
    processor = get_processor()
    app.run(debug=True, use_reloader=False)
