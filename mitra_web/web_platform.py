from flask import Flask, render_template, jsonify, Response
import requests, time, os

app = Flask(__name__, template_folder="templates")

PI_VIDEO = "http://192.168.115.68:5000/video"
PI_DETECT = "http://192.168.115.68:5000/detect"
PI_LANE = "http://192.168.115.68:5010/video_feed"
PI_LANE_STATE = "http://192.168.115.68:5010/lane_state"

MAC_ASSISTANT = "http://192.168.115.241:6000/ask"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/video")
def video():
    def gen():
        r = requests.get(PI_VIDEO, stream=True)
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                yield chunk
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/detections")
def detections():
    try:
        return jsonify(requests.get(PI_DETECT, timeout=2).json())
    except:
        return jsonify([])

@app.route("/lane")
def lane():
    def gen():
        r = requests.get(PI_LANE, stream=True)
        for c in r.iter_content(chunk_size=1024):
            if c:
                yield c
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/lane_state")
def lane_state():
    try:
        return jsonify(requests.get(PI_LANE_STATE, timeout=2).json())
    except:
        return jsonify({})

@app.route("/speak", methods=["POST"])
def speak():
    data = {"query": "describe the scene", "detections": [], "status": {}}
    try:
        r = requests.post(MAC_ASSISTANT, json=data, timeout=10)
        return jsonify(r.json())
    except:
        return jsonify({"reply": "(assistant unreachable)"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
#!/usr/bin/env python3
from flask import Flask, render_template, jsonify, request, Response
import requests, os

PI_DETECTIONS = "http://127.0.0.1:5000/latest_detections"
PI_VIDEO      = "http://127.0.0.1:5010/video_feed"
PI_LANE       = "http://127.0.0.1:5010/lane_state"
MAC_ASSISTANT = "http://__MAC__/ask"

app = Flask(__name__, template_folder='templates')

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/video_feed_stream')
def video_feed_stream():
    def generate():
        r = requests.get(PI_VIDEO, stream=True)
        for c in r.iter_content(1024):
            if c: yield c
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route('/api/latest_detections')
def latest():
    try:
        return jsonify(requests.get(PI_DETECTIONS).json())
    except: return jsonify([])

@app.route('/api/lane_state')
def lane():
    try:
        return jsonify(requests.get(PI_LANE).json())
    except: return jsonify({})

@app.route('/api/speak', methods=['POST'])
def speak():
    data = request.json
    try:
        r = requests.post(MAC_ASSISTANT, json=data, timeout=5)
        return jsonify(r.json())
    except:
        return jsonify({"reply": "(error) cannot reach Mac assistant"})

if __name__ == '__main__':
    MAC = os.environ.get("MITRA_MAC", "http://__MAC__:6000")
    MAC_ASSISTANT = MAC + "/ask"
    print("Mitra Web running on port 5001")
    app.run(host="0.0.0.0", port=5001)
