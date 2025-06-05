import sys
import cv2
import threading
import time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QSlider, QLabel,
    QVBoxLayout, QHBoxLayout, QComboBox, QPushButton
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QImage


class CameraStream:
    def __init__(self, cam_index, delay_sec=0):
        self.cap = cv2.VideoCapture(cam_index)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        self.fps = 60
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        self.delay_sec = delay_sec
        self.buffer = []
        self.running = True
        self.frame = None
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()

    def update(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue
            timestamp = time.time()
            with self.lock:
                self.buffer.append((timestamp, frame))
                while self.buffer and (timestamp - self.buffer[0][0]) > self.delay_sec:
                    self.buffer.pop(0)
                self.frame = self.buffer[0][1] if self.buffer else frame
            time.sleep(1 / self.fps)

    def get_frame(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def set_delay(self, delay_sec):
        with self.lock:
            self.delay_sec = delay_sec

    def release(self):
        self.running = False
        self.thread.join()
        self.cap.release()


class VideoWidget(QWidget):
    def __init__(self, cameras):
        super().__init__()
        self.cameras = cameras
        # 個別の高さを保持（デフォルト480で初期化）
        self.video_widths = [640 for _ in cameras]
        self.video_heights = [0 for _ in cameras]
        self.columns = 2  # 横に並べる台数

    def paintEvent(self, event):
        painter = QPainter(self)
        spacing = 10  # 映像同士の間隔
        y = [0 for _ in range(self.columns)]

        for i, cam in enumerate(self.cameras):
            frame = cam.get_frame()
            if frame is None:
                continue

            w = self.video_widths[i]
            h = int(w * frame.shape[0] / frame.shape[1])
            resized = cv2.resize(frame, (w, h))
            img = self.cv_to_qimage(resized)

            # 行と列を計算（2列配置）
            row = i // self.columns
            col = i % self.columns

            x = 0

            if col == self.columns - 1:
                x = x + self.video_widths[i-1] + spacing

            painter.drawImage(x, y[col], img)
            
            y[col] = y[col] + h + spacing


    def cv_to_qimage(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)

    # 複数の高さを一括でセット
    def set_video_widths(self, widths):
        self.video_widths = widths
        self.update()


class ControlWindow(QWidget):
    def __init__(self, cameras, video_widget, apply_camera_change_callback, open_control_window_callback):
        super().__init__()
        self.setWindowTitle("Controls")
        self.cameras = cameras
        self.video_widget = video_widget
        self.apply_camera_change_callback = apply_camera_change_callback
        self.open_control_window_callback = open_control_window_callback

        self.num_cameras = len(cameras)
        self.camera_selectors = []
        self.width_sliders = []

        layout = QVBoxLayout()

        self.combo_layout = QHBoxLayout()
        for i in range(self.num_cameras):
            combo = QComboBox()
            combo.addItems([str(i) for i in range(10)])
            combo.setCurrentIndex(i)
            self.combo_layout.addWidget(QLabel(f"Camera {i+1}:"))
            self.combo_layout.addWidget(combo)
            self.camera_selectors.append(combo)
        self.button_apply = QPushButton("Apply")
        self.button_apply.clicked.connect(self.apply_camera_change_callback)
        self.combo_layout.addWidget(self.button_apply)
        layout.addLayout(self.combo_layout)

        for i in range(self.num_cameras):
            slider = QSlider(Qt.Horizontal)
            slider.setRange(480, 1920)
            slider.setValue(640)
            slider.valueChanged.connect(self.update_slider_values)
            layout.addWidget(QLabel(f"Camera {i+1} Width"))
            layout.addWidget(slider)
            self.width_sliders.append(slider)

        self.slider_delay = QSlider(Qt.Horizontal)
        self.slider_delay.setRange(0, 400)
        self.slider_delay.setValue(0)
        self.slider_delay.valueChanged.connect(self.update_delay)
        layout.addWidget(QLabel("Common Delay (sec)"))
        layout.addWidget(self.slider_delay)

        self.setLayout(layout)

    def update_slider_values(self):
        widths = [s.value() for s in self.width_sliders]
        self.video_widget.set_video_widths(widths)

    def update_delay(self):
        delay = self.slider_delay.value() / 10.0
        for cam in self.cameras:
            cam.set_delay(delay)

    def get_selected_camera_indices(self):
        return [int(cb.currentText()) for cb in self.camera_selectors]
    
    def closeEvent(self):
        self.open_control_window_callback()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-Camera Viewer")
        self.resize(800, 600)
        self.running = True

        # 初期カメラ構成
        self.cameras = [CameraStream(i) for i in range(2)]
        self.video_widget = VideoWidget(self.cameras)

        layout = QVBoxLayout()
        layout.addWidget(self.video_widget)
        self.setLayout(layout)

        # コントロールウィンドウを生成
        self.open_control_window()

        self.timer = QTimer()
        self.timer.timeout.connect(self.video_widget.update)
        self.timer.start(16)

    def change_cameras(self):
        indices = self.control_window.get_selected_camera_indices()
        for cam in self.cameras:
            cam.release()
        self.cameras = [CameraStream(i) for i in indices]
        self.video_widget.cameras = self.cameras
        self.control_window.cameras = self.cameras  # コントロール側にも更新

    def open_control_window(self):
        if self.running:
            self.control_window = ControlWindow(
                self.cameras,
                self.video_widget,
                self.change_cameras,
                self.open_control_window
            )
            self.control_window.show()

    def closeEvent(self, a0):
        self.running = False
        if self.control_window.isVisible():
            self.control_window.close()
        return super().closeEvent(a0)
    

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
