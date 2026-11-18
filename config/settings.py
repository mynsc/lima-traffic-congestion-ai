VERDE_MIN = 15
VERDE_MAX = 60
AMARILLO = 3
VERDE_FIJO = 30
VERDE_EMERGENCIA = 15
PESO_AUTO = 2.5
PESO_BUS = 5.0
BASE_VERDE = 5
CONF_THRESHOLD = 0.4
FRAME_SKIP = 2
IMGSZ = 640
MODEL_PATH = "models/yolov8n.pt"
DB_PATH = "data/traffic_system.db"
VIDEO_PATH = "data/videos/sample.mp4"

ROIS = {
    "Calle_A": [(80, 320), (520, 320), (600, 700), (20, 700)],
    "Calle_B": [(680, 320), (1200, 320), (1260, 700), (620, 700)],
}