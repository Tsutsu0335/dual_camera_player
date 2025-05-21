import sys
import cv2
import threading
import time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QSlider, QLabel,
    QVBoxLayout, QHBoxLayout, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QImage


class CameraStream:
    def __init__(self, cam_index, delay_sec=0):
        self.cap = cv2.VideoCapture(cam_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS, 60)
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
            time.sleep(1 / 60)

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
    def __init__(self, cam1: CameraStream, cam2: CameraStream):
        super().__init__()
        self.cam1 = cam1
        self.cam2 = cam2
        self.main_height = 720
        self.sub_height = 360

    def paintEvent(self, event):
        painter = QPainter(self)
        frame1 = self.cam1.get_frame()
        if frame1 is not None:
            mh = self.main_height
            mw = int(mh * 16 / 9)
            resized1 = cv2.resize(frame1, (mw, mh))
            img1 = self.cv_to_qimage(resized1)
            painter.drawImage(0, 0, img1)

            frame2 = self.cam2.get_frame()
            if frame2 is not None:
                rotated = cv2.rotate(frame2, cv2.ROTATE_90_CLOCKWISE)
                h, w, _ = rotated.shape
                sh = self.sub_height
                sw = int(sh * w / h)
                resized2 = cv2.resize(rotated, (sw, sh))
                painter.drawImage(mw + 10, 0, self.cv_to_qimage(resized2))

    def cv_to_qimage(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)

    def set_main_height(self, h):
        self.main_height = h
        self.update()

    def set_sub_height(self, h):
        self.sub_height = h
        self.update()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dual Camera with Delay and Adjustable Sizes")
        self.resize(1000, 600)

        self.cam1 = CameraStream(1)
        self.cam2 = CameraStream(2)
        self.video_widget = VideoWidget(self.cam1, self.cam2)

        self.slider_main_size = QSlider(Qt.Horizontal)
        self.slider_main_size.setRange(360, 1080)
        self.slider_main_size.setValue(720)

        self.slider_sub_size = QSlider(Qt.Horizontal)
        self.slider_sub_size.setRange(360, 1080)
        self.slider_sub_size.setValue(640)

        self.slider_delay = QSlider(Qt.Horizontal)
        self.slider_delay.setRange(0, 300)
        self.slider_delay.setValue(0)
        self.input_delay = QLineEdit("0.0")
        self.input_delay.setFixedWidth(50)


        self.slider_delay.valueChanged.connect(
            lambda val: self.input_delay.setText(f"{val / 10.0:.1f}")
        )

        self.input_delay.editingFinished.connect(
            lambda: self.slider_delay.setValue(int(float(self.input_delay.text()) * 10))
        )

        slider_layout = QVBoxLayout()
        for label_text, slider, input_box in [
            ("Main Video Height", self.slider_main_size, None),
            ("Sub Video Height", self.slider_sub_size, None),
            ("Main Delay (sec)", self.slider_delay, self.input_delay),
        ]:
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel(label_text))
            hbox.addWidget(slider)
            if input_box:
                hbox.addWidget(input_box)
            slider_layout.addLayout(hbox)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.video_widget)
        main_layout.addLayout(slider_layout)

        self.setLayout(main_layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.on_timer)
        self.timer.start(16)

    def on_timer(self):
        self.video_widget.set_main_height(self.slider_main_size.value())
        self.video_widget.set_sub_height(self.slider_sub_size.value())
        self.cam1.set_delay(self.slider_delay.value() / 10.0)
        self.cam2.set_delay(self.slider_delay.value() / 10.0)
        self.video_widget.update()

    def closeEvent(self, event):
        self.cam1.release()
        self.cam2.release()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
