#!/usr/bin/env python3
"""
Replacement web_detect_status.py
- video feed at /video_feed (multipart JPEG)
- latest detections at /latest_detections (JSON)
- /chat forwards to ASSISTANT_REMOTE (env var MITRA_MAC_ASSISTANT or default)
- simple SSE listener on /events
- If model files missing, script runs with empty detections (graceful)
"""
from flask import Flask, Response, render_template, request, jsonify, stream_with_context
import threading, time, cv2, numpy as np, os, queue, requests, subprocess, traceback

app = Flask(__name__, template_folder='templates')

# Config - change if needed or set MITRA_MAC_ASSISTANT env var
ASSISTANT_REMOTE = os.environ.get("MITRA_MAC_ASSISTANT", "http://192.168.115.241:6000/ask")

PROTO = "MobileNetSSD_deploy.prototxt"
MODEL = "MobileNetSSD_deploy.caffemodel"
CAM_INDICES = [0, 1]
CAM_WIDTH = 640
CAM_HEIGHT = 480
CONFIDENCE_DEFAULT = 0.5

# classes (MobileNet SSD)
CLASSES = ["background","aeroplane","bicycle","bird","boat","bottle","bus","car","cat","chair",
           "cow","diningtable","dog","horse","motorbike","person","pottedplant","sheep","sofa","train","tvmonitor"]

# Global state
frame_lock = threading.Lock()
output_frame = None
latest_detections = []
current_confidence = CONFIDENCE_DEFAULT
listeners = []
status_data = {"lat": None, "lon": None, "temp": None}

def notify_listeners(message: str):
    dead = []
    for q in listeners:
        try:
            q.put_nowait(message)
        except Exception:
            dead.append(q)
    for q in dead:
        try:
            listeners.remove(q)
        except Exception:
            pass

def open_camera(tried=None):
    tried = tried or []
    for idx in CAM_INDICES:
        if idx in tried:
            continue
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            try:
                cap.open(idx)
            except:
                pass
        if cap.isOpened():
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
            except:
                pass
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or CAM_WIDTH)
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or CAM_HEIGHT)
            print(f"[INFO] camera opened index={idx} => {w}x{h}")
            return cap
    print("[WARN] no camera opened for indices", CAM_INDICES)
    return None

def load_model():
    if os.path.exists(PROTO) and os.path.exists(MODEL):
        try:
            net = cv2.dnn.readNetFromCaffe(PROTO, MODEL)
            print("[INFO] loaded MobileNetSSD model")
            return net
        except Exception:
            print("[WARN] failed to load DNN model:", traceback.format_exc())
            return None
    else:
        print("[WARN] model files not found, detection disabled (run without model)")
        return None

def camera_loop():
    global output_frame, latest_detections, current_confidence
    net = load_model()
    vs = open_camera()
    if vs is None:
        print("[ERROR] camera failed to open; camera_loop exiting")
        return
    time.sleep(0.5)
    while True:
        try:
            ret, frame = vs.read()
            if not ret:
                time.sleep(0.05)
                continue
            (h, w) = frame.shape[:2]
            detections_out = []
            if net is not None:
                blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300,300)), 0.007843, (300,300), 127.5)
                net.setInput(blob)
                detections = net.forward()
                for i in range(detections.shape[2]):
                    conf = float(detections[0,0,i,2])
                    if conf < current_confidence:
                        continue
                    idx = int(detections[0,0,i,1])
                    if idx < 0 or idx >= len(CLASSES):
                        continue
                    (sx, sy, ex, ey) = (detections[0,0,i,3:7] * np.array([w,h,w,h])).astype("int")
                    cls = CLASSES[idx]
                    detections_out.append({"class": cls, "conf": conf, "bbox":[int(sx),int(sy),int(ex),int(ey)]})
                    color = (0,255,0)
                    cv2.rectangle(frame, (sx,sy), (ex,ey), color, 2)
                    y = sy - 10 if sy - 10 > 10 else sy + 10
                    cv2.putText(frame, f"{cls} {conf*100:.0f}%", (sx,y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            latest_detections = detections_out
            with frame_lock:
                _, jpeg = cv2.imencode('.jpg', frame)
                output_frame = jpeg.tobytes()
            if detections_out:
                payload = "\n".join([f"DETECT|{time.strftime('%Y-%m-%d %H:%M:%S')}|{d['class']}|{d['conf']:.3f}" for d in detections_out])
                notify_listeners(payload)
            time.sleep(0.02)
        except Exception:
            print("[ERROR] camera_loop exception:", traceback.format_exc())
            time.sleep(0.5)

@app.route('/events')
def events():
    def stream():
        q = queue.Queue()
        listeners.append(q)
        try:
            while True:
                data = q.get()
                yield f"data: {data}\n\n"
        except GeneratorExit:
            pass
        finally:
            try:
                listeners.remove(q)
            except Exception:
                pass
    return Response(stream_with_context(stream()), mimetype='text/event-stream')

@app.route('/latest_detections')
def latest():
    return jsonify(latest_detections)

@app.route('/video_feed')
def video_feed():
    def gen():
        global output_frame
        while True:
            with frame_lock:
                if output_frame is None:
                    time.sleep(0.05)
                    continue
                b = output_frame
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + b + b'\r\n')
            time.sleep(0.03)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True)
    q = data.get('query','')
    payload = {"query": q, "detections": latest_detections, "status": status_data, "image_caption": None}
    try:
        r = requests.post(ASSISTANT_REMOTE, json=payload, timeout=20)
        reply = r.json().get('reply','(no reply)')
    except Exception as e:
        reply = f"(assistant error) {e}"
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    notify_listeners(f"ASSISTANT|{ts}|{reply}")
    # Do not run local TTS here (Mac speaks); keep safe
    return jsonify({"reply": reply})

@app.route('/update_status', methods=['POST'])
def update_status():
    global status_data
    j = request.get_json(force=True)
    if isinstance(j, dict):
        status_data.update(j)
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    notify_listeners(f"STATUS|{ts}|{status_data}")
    return jsonify({"ok": True})

@app.route('/')
def index():
    return "<html><body><h3>web_detect_status running</h3></body></html>"

if __name__ == '__main__':
    t = threading.Thread(target=camera_loop, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=5000, threaded=True)
