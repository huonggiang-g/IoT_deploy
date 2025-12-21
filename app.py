#pip install flask paho-mqtt flask_socketio firebase_admin
import eventlet
eventlet.monkey_patch()

import firebase_admin
from firebase_admin import credentials, db
import json, os
from collections import Counter

firebase_json = json.loads(os.environ["FIREBASE_CONFIG"])
cred = credentials.Certificate(firebase_json)

firebase_admin.initialize_app(cred, {
    "databaseURL": "https://etone-3f7df-default-rtdb.asia-southeast1.firebasedatabase.app/" #Giang
    # "databaseURL": "https://etone1-1b551-default-rtdb.asia-southeast1.firebasedatabase.app/" 
})
###############################################################

from flask import Flask, render_template, request, session, redirect
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt #pip install paho-mqtt
from functools import wraps


app = Flask(__name__)
app.secret_key = "secret"
# socketio = SocketIO(app, cors_allowed_origins="*")
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet"
)


# ========== MQTT CONFIG ==========
MQTT_HOST = "" #Giang
MQTT_HOST = "e539507d822e4b348dc6f0af2600bd01.s1.eu.hivemq.cloud" #Giang
# MQTT_HOST = "0270d20e699d416488126e9f9561de38.s1.eu.hivemq.cloud" 
MQTT_PORT = 8883
MQTT_USER = "etone"
MQTT_PASS = "Eto12345"

def on_message(client, userdata, msg):
    payload = msg.payload.decode().strip()
    try:
        data = json.loads(payload)
        print("Json from ESP8266: ", data)
        # Gửi realtime đến web
        socketio.emit("robot_update", data)

        ref = db.reference("/robot_data")   # node trong DB
        ref.push(data)                      # lưu vào Firebase
    except json.JSONDecodeError:
        # Nếu lỗi, đây là chuỗi thường
        print("String from ESP:", payload)

mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.tls_set()
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_HOST, MQTT_PORT)
mqtt_client.subscribe("esp8266/dht11")
mqtt_client.publish("esp8266/client", "test_from_render")

mqtt_client.loop_start()
# ===================================


@app.context_processor
def inject_user():
    return {
        "username": session.get("username"),
        "role": session.get("role")
    }


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect("/login")
        return fn(*args, **kwargs)
    return wrapper


def operator_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "operator":
            return redirect("/")
        return fn(*args, **kwargs)
    return wrapper

@socketio.on('send_command')
def handle_command(data):
    print("CMD from web: ", data)
    mqtt_client.publish("esp8266/client", json.dumps(data))
    # mqtt_client.publish("esp8266/client", data)

@app.route("/")
@login_required
def home():
    return render_template("index.html")

@app.route("/users", methods=["GET", "POST"])
@login_required
@operator_required
def users():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        ref = db.reference(f"users/{username}")

        if ref.get():
            return "User existed"

        ref.set({
            "password": password,
            "role": role
        })

        return "OK!"

    ref = db.reference("users")
    users = ref.get() or {}

    return render_template("users.html", users=users)

@app.route("/users/update/<username>", methods=["POST"])
@login_required
@operator_required
def update_user(username):
    role = request.form["role"]

    db.reference(f"users/{username}/role").set(role)

    return redirect("/users")

@app.route("/users/delete/<username>")
@login_required
@operator_required
def delete_user(username):
    db.reference(f"users/{username}").delete()
    return redirect("/users")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        ref = db.reference(f"users/{username}")
        user = ref.get()

        if not user or user["password"] != password:
            return "wrong"

        session["username"] = username
        session["role"] = user["role"]

        return redirect("/")
        

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/database", methods=["GET"])
@login_required
def database():
    ref = db.reference("robot_data")
    data = ref.get() or {}

    stats = Counter()

    for item in data.values():
        action = item.get("action")
        if action:
            stats[action] += 1

    return render_template(
        "database.html",
        data=data,
        stats=stats
    )

port = int(os.environ.get("PORT", 5000))
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=port)
