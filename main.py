import sys
import os
import cv2
import threading
import time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QSlider, QLabel, QHBoxLayout,
    QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QImage


class CameraStream:
    def __init__(self, cam_index, delay_sec=0):
        self.cap = cv2.VideoCapture(cam_index)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.fps = 60
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        self.cam_index = cam_index
        self.delay_sec = delay_sec
        self.buffer = []
        self.running = True
        self.frame = None
        self.delay_frame = None
        self.recording = False
        self.writer = None
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
                self.frame = frame
                self.delay_frame = self.buffer[0][1] if self.buffer else frame
            
                if self.recording and self.writer is not None:
                    self.writer.write(frame)


            time.sleep(1 / self.fps)

    def get_frame(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def get_delay_frame(self):
        with self.lock:
            return self.delay_frame.copy() if self.delay_frame is not None else None

    def set_delay(self, delay_sec):
        with self.lock:
            self.delay_sec = delay_sec
    
    def start_recording(self, output_path):
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self.writer = cv2.VideoWriter(output_path, fourcc, self.fps / 2,(
            int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        ))
        self.recording = True
    
    def stop_recording(self):
        self.recording = False
        with self.lock:
            if self.writer is not None:
                self.writer.release()
                self.writer = None

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
    def __init__(self, cameras, video_widget, apply_camera_change_callback, open_control_window_callback, toggle_recording_callback):
        super().__init__()
        self.setWindowTitle("Controls")
        self.cameras = cameras
        self.video_widget = video_widget
        self.apply_camera_change_callback = apply_camera_change_callback
        self.open_control_window_callback = open_control_window_callback
        self.toggle_recording_callback = toggle_recording_callback

        self.num_cameras = len(cameras)
        self.camera_selectors = []
        self.width_sliders = []

        layout = QVBoxLayout()

        self.combo_layout = QHBoxLayout()
        for i in range(self.num_cameras):
            combo = QComboBox()
            combo.addItems([str(i) for i in range(self.num_cameras)])
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

        delay_layout = QHBoxLayout()
        self.slider_delay = QSlider(Qt.Horizontal)
        self.slider_delay.setRange(0, 400)
        self.slider_delay.setValue(0)
        self.slider_delay.valueChanged.connect(self.update_slider_delay)
        self.input_delay = QLineEdit(str(self.slider_delay.value()))
        self.input_delay.setFixedWidth(50)
        self.input_delay.textEdited.connect(self.update_input_delay_values)
        layout.addWidget(QLabel("Common Delay (100 msec)"))
        delay_layout.addWidget(self.slider_delay)
        delay_layout.addWidget(self.input_delay)
        layout.addLayout(delay_layout)

        layout.addWidget(QLabel("Recording"))
        self.record_button = QPushButton("Start")
        self.record_button.clicked.connect(self.toggle_recording_callback)
        layout.addWidget(self.record_button)

        self.setLayout(layout)

    def update_slider_values(self):
        widths = [s.value() for s in self.width_sliders]
        self.video_widget.set_video_widths(widths)
        
    def update_input_delay_values(self):
        self.slider_delay.setValue(int(self.input_delay.text()))

    def update_slider_delay(self, val):
        delay = self.slider_delay.value() / 10.0
        for cam in self.cameras:
            cam.set_delay(delay)
        self.input_delay.setText(str(val))


    def get_selected_camera_indices(self):
        return [int(cb.currentText()) for cb in self.camera_selectors]
    
    def closeEvent(self, _):
        self.open_control_window_callback()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-Camera Viewer")
        self.resize(800, 600)
        self.running = True
        self.recording = False

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

    def toggle_recording(self):
        if not self.recording:
            timestamp = int(time.time())
            os.mkdir(f"videos/{timestamp}")
            for i, cam in enumerate(self.cameras):
                filename = f"videos/{timestamp}/record_{timestamp}_camera_{i}.avi"
                cam.start_recording(filename)
            self.recording = True
            self.control_window.record_button.setText("Stop")
        
        else:
            for cam in self.cameras:
                cam.stop_recording()
            self.recording = False
            self.control_window.record_button.setText("Start")
            

    def open_control_window(self):
        if self.running:
            self.control_window = ControlWindow(
                self.cameras,
                self.video_widget,
                self.change_cameras,
                self.open_control_window,
                self.toggle_recording
            )
            self.control_window.show()

    def closeEvent(self, _):
        self.running = False
        if self.control_window.isVisible():
            self.control_window.close()
        return super().closeEvent(_)
    
if __name__ == "__main__":
    try:
        os.mkdir("./videos")
    except:
        pass

    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
