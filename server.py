from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
import bcrypt
import uuid
import base64
from PIL import Image
from io import BytesIO
import face_recognition

app = Flask(__name__)
CORS(app)

# Directory setup
UPLOAD_FOLDER = "uploads"
USER_SELFIES = os.path.join(UPLOAD_FOLDER, "selfies")
ADMIN_PHOTOS = os.path.join(UPLOAD_FOLDER, "admin")
ADMIN_FILE = "admin_password.json"

os.makedirs(USER_SELFIES, exist_ok=True)
os.makedirs(ADMIN_PHOTOS, exist_ok=True)


# Load or initialize admin password
def load_admin_password():
    if not os.path.exists(ADMIN_FILE):
        # Default password: admin123
        default_hashed = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        with open(ADMIN_FILE, 'w') as f:
            json.dump({"password": default_hashed}, f)
    with open(ADMIN_FILE, 'r') as f:
        return json.load(f)["password"]


def update_admin_password(new_password):
    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    with open(ADMIN_FILE, 'w') as f:
        json.dump({"password": hashed}, f)


# Helpers
def decode_base64_image(base64_str):
    header, encoded = base64_str.split(",", 1)
    return Image.open(BytesIO(base64.b64decode(encoded)))


def save_image(img, folder):
    filename = f"{uuid.uuid4().hex}.jpg"
    path = os.path.join(folder, filename)
    img.save(path)
    return path


def encode_faces_in_folder(folder):
    encodings = []
    paths = []
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        img = face_recognition.load_image_file(path)
        faces = face_recognition.face_locations(img)
        if not faces:
            continue
        encoding = face_recognition.face_encodings(img, faces)[0]
        encodings.append(encoding)
        paths.append(path)
    return encodings, paths


# Routes

@app.route("/")
def index():
    # Serve frontend html (in templates folder)
    return send_from_directory("templates", "ai-app.html")


@app.route("/login-admin", methods=["POST"])
def login_admin():
    data = request.get_json()
    entered = data.get("password")
    stored_hash = load_admin_password()
    if bcrypt.checkpw(entered.encode(), stored_hash.encode()):
        return jsonify({"success": True})
    return jsonify({"success": False}), 401


@app.route("/update-admin-password", methods=["POST"])
def change_password():
    data = request.get_json()
    new_password = data.get("new_password")
    update_admin_password(new_password)
    return jsonify({"success": True, "message": "Password updated"})


@app.route("/upload-admin-photo", methods=["POST"])
def upload_admin_photo():
    data = request.get_json()
    image_data = data.get("image")
    if not image_data:
        return jsonify({"success": False, "error": "No image data provided"}), 400
    img = decode_base64_image(image_data)
    save_image(img, ADMIN_PHOTOS)
    return jsonify({"success": True})


@app.route("/upload-selfie", methods=["POST"])
def upload_selfie():
    data = request.get_json()
    image_data = data.get("image")
    if not image_data:
        return jsonify({"matches": [], "error": "No image data provided"}), 400

    img = decode_base64_image(image_data)
    selfie_path = save_image(img, USER_SELFIES)

    try:
        guest_img = face_recognition.load_image_file(selfie_path)
        encodings = face_recognition.face_encodings(guest_img)
        if not encodings:
            return jsonify({"matches": [], "error": "Face not detected"}), 400
        guest_encoding = encodings[0]
    except Exception as e:
        return jsonify({"matches": [], "error": "Processing failed", "details": str(e)}), 400

    matches = []
    admin_encodings, admin_paths = encode_faces_in_folder(ADMIN_PHOTOS)

    for encoding, path in zip(admin_encodings, admin_paths):
        match = face_recognition.compare_faces([encoding], guest_encoding, tolerance=0.5)[0]
        if match:
            with open(path, "rb") as f:
                base64_img = base64.b64encode(f.read()).decode()
                matches.append(f"data:image/jpeg;base64,{base64_img}")

    return jsonify({"matches": matches})


if __name__ == "__main__":
    app.run(debug=True)
