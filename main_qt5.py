import sys
import os
import time
import shutil

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QWidget, QLineEdit,
    QVBoxLayout, QHBoxLayout, QSlider, QLabel, QComboBox, QCheckBox,
    QTabWidget, QFileDialog, QAction
)
from PyQt5.QtGui import QPainter, QImage, QColor
from PyQt5.QtCore import QTimer, Qt

from flowlayout_qt5 import FlowLayout, clear_layout
from camera import CameraStream, detect_available_cameras

import cv2

tmp_dir = "./.tmp_videos"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Camera Player")

        #--- central widget ---
        self.central_widget = VideosWidget([0, 1])
        self.setCentralWidget(self.central_widget)
        #--- central widget ---

        #--- menu bar (status bar) ---
        self.statusbar = self.statusBar()
        self.statusbar.showMessage(f"Delay: {self.central_widget.delay_sec}sec, Recording: {self.central_widget.recording}")

        self.menubar = self.menuBar()
        self.menubar.setNativeMenuBar(False)

        self.menu_file = self.menubar.addMenu("File")
        self.menu_file_setting = QAction("Setting", self)
        self.menu_file.addAction(self.menu_file_setting)
        self.menu_file_setting.triggered.connect(self.central_widget.open_setting_window)
        #--- menu bar (status bar) ---

        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def keyPressEvent(self, event):
        if event.key() == ord("1"):
            self.central_widget.update_delay(self.central_widget.delay_sec - 1)
        
        if event.key() == ord("2"):
            self.central_widget.update_delay(self.central_widget.delay_sec + 1)

        if event.key() == ord("3"):
            self.central_widget.toggle_record()
        
        self.statusbar.showMessage(f"Delay: {self.central_widget.delay_sec}sec, Recording: {self.central_widget.recording}")

    
    def closeEvent(self, _):
        if self.central_widget.setting_window is not None and self.central_widget.setting_window.isVisible():
            self.central_widget.setting_window.close()
        return super().closeEvent(_)
        
class VideosWidget(QWidget):
    def __init__(self, cam_indexes: list):
        super().__init__()
        self.available_cameras = detect_available_cameras()

        self.layout = FlowLayout()
        self.cam_indexes = cam_indexes
        self.video_widgets = []
        self.setting_window = None
        self.recording = False
        self.filenames = []
        self.delay_sec = 0
        
        self.tmp_dir = tmp_dir

        self.reload()

        self.setLayout(self.layout)

    def reload(self):
        self.stop_record()

        for video_widget in self.video_widgets:
            self.layout.removeWidget(video_widget)
            video_widget.close()
            video_widget.deleteLater()

        self.video_widgets = []

        for cam_index in self.cam_indexes:
            self.video_widgets.append(VideoWidget(cam_index))
            self.layout.addWidget(self.video_widgets[-1])


    def set_cam_indexes(self, cam_indexes):
        self.cam_indexes = cam_indexes

    def open_setting_window(self):
        self.setting_window = SettingWindow(
            cam_indexes=self.cam_indexes,
            videos_widget=self,
            available_cameras=self.available_cameras
        )
        self.setting_window.show()

    def start_record(self):
        if self.recording:
            print("recording is already running")
            return
        
        
        self.filenames = []
        try:
            os.mkdir(tmp_dir)
        except:
            pass

        now_time = int(time.time())

        for i, video_widget in enumerate(self.video_widgets):
            filename = f"record_{now_time}_camera{i}.avi"
            video_widget.start_record(os.path.join(self.tmp_dir, filename))
            self.filenames.append(filename)
        
        self.recording = True

    def stop_record(self):
        if not self.recording:
            return
                
        for i, video_widget in enumerate(self.video_widgets):
            video_widget.stop_record()

        dst_dir = QFileDialog.getExistingDirectory()
        for src_name in self.filenames:
            shutil.move(os.path.join(self.tmp_dir, src_name), os.path.join(dst_dir, src_name))

        self.recording = False

    def update_delay(self, delay_sec):
        self.delay_sec = min(max(0, delay_sec), self.video_widgets[0].delay_sec_max)
        for video_widget in self.video_widgets:
            video_widget.set_delay_sec(self.delay_sec)

    def toggle_record(self):
        if self.recording:
            self.stop_record()
        else:
            self.start_record()

class VideoWidget(QWidget):
    def __init__(self, cam_index: int, width=640, height=360, delay_sec_max=45, resolution=(1280, 720)):
        super().__init__()
        self.camera_stream = CameraStream(cam_index, height=resolution[1], width=resolution[0], delay_sec_max=delay_sec_max)
        self.camera_stream.start()
        self.width = width
        self.height = height
        self.delay_sec_max = delay_sec_max
        self.setMinimumSize(self.width, self.height)
        self.cross_flag = False
        self.cross_x = 0.5
        self.cross_y = 0.5

    def paintEvent(self, event):
        painter = QPainter(self)
        frame = self.camera_stream.get_frame()
        if frame is None:
            return
        
        resized = cv2.resize(frame, (self.width, self.height))
        img = self.cv_to_qimage(resized)

        painter.drawImage(0, 0, img)

        if self.cross_flag:
            painter.setPen(QColor(255,0,0))
            painter.drawLine(0, int(self.height * self.cross_y), self.width, int(self.height * self.cross_y))
            painter.drawLine(int(self.width * self.cross_x), 0, int(self.width * self.cross_x), self.height)

    def set_delay_sec(self, sec: int):
        self.camera_stream.set_delay(sec)

    def set_video_widget_width(self, width):
        self.width = width
        self.height = int(width * 9 / 16)
        self.setMinimumSize(self.width, self.height)
    
    def set_cross_flag(self, f: bool):
        self.cross_flag = f
    
    def set_cross_x(self, x):
        self.cross_x = x * 0.01
    
    def set_cross_y(self, y):
        self.cross_y = y * 0.01

    def start_record(self, filename):
        self.camera_stream.start_recording(filename)
    
    def stop_record(self):
        self.camera_stream.stop_recording()


    def cv_to_qimage(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    
    def closeEvent(self, _):
        self.camera_stream.release()
        return super().closeEvent(_)


class SettingWindow(QMainWindow):
    def __init__(self, cam_indexes, videos_widget, available_cameras):
        super().__init__()
        self.setWindowTitle("Setting")
        self.resize(600, 500)
        self.cam_indexes = cam_indexes
        self.videos_widget = videos_widget
        self.available_cameras = available_cameras

        self.central_widget = QTabWidget()
        self.setCentralWidget(self.central_widget)
        
        self.camera_tab_widget = QWidget()
        self.camera_tab_layout = QVBoxLayout()
        self.camera_tab_widget.setLayout(self.camera_tab_layout)
        self.central_widget.addTab(self.camera_tab_widget, "Camera")
        
        self.view_tab_widget = QWidget()
        self.view_tab_layout = QVBoxLayout()
        self.view_tab_widget.setLayout(self.view_tab_layout)
        self.central_widget.addTab(self.view_tab_widget, "View")

        self.record_tab_widget = QWidget()
        self.record_tab_layout = QVBoxLayout()
        self.record_tab_widget.setLayout(self.record_tab_layout)
        self.central_widget.addTab(self.record_tab_widget, "Record")

        self.camera_num_combo = QComboBox()

        self.tab_layouts = [self.camera_tab_layout, self.view_tab_layout, self.record_tab_layout]
        self.camera_idx_combos = []
        self.width_sliders = []
        self.delay_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_textbox = QLineEdit()
        self.cross_x_sliders = []
        self.cross_y_sliders = []

        self.reload()
        
        
    def reload(self):
        for layout in self.tab_layouts:
            clear_layout(layout)

        self.camera_idx_combos = []
        self.width_sliders = []
        self.cross_x_sliders = []
        self.cross_y_sliders = []

        #--- camera num combo ---
        camera_num_layout = QHBoxLayout()
        self.camera_num_combo = QComboBox()
        self.camera_num_combo.addItems([str(i) for i in range(1, len(self.available_cameras)+1)])
        self.camera_num_combo.setCurrentIndex(len(self.cam_indexes) - 1)
        
        camera_num_layout.addWidget(QLabel(f"Number of cameras:"))
        camera_num_layout.addWidget(self.camera_num_combo)

        self.camera_tab_layout.addLayout(camera_num_layout)
        #--- camera num combo ---


        #--- camera index combo ---
        camera_idx_layout = QHBoxLayout()
        camera_idx_layout.addWidget(QLabel("Camera ID: "))
        for i, cam_idx in enumerate(self.cam_indexes):
            camera_idx_combo = QComboBox()
            camera_idx_combo.addItems(self.available_cameras)
            camera_idx_combo.setCurrentIndex(cam_idx)
            camera_idx_layout.addWidget(QLabel(f"Camera {i}"))
            camera_idx_layout.addWidget(camera_idx_combo)

            self.camera_idx_combos.append(camera_idx_combo)

        self.camera_tab_layout.addLayout(camera_idx_layout)

        #--- camera index combo ---


        camera_conf_apply_button = QPushButton("Apply")
        camera_conf_apply_button.clicked.connect(self.update_camera_num)
        self.camera_tab_layout.addWidget(camera_conf_apply_button)
        

        #--- camera delay slider ---
        delay_layout = QHBoxLayout()
        self.delay_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_slider.setRange(0, 40)
        self.delay_slider.setValue(self.videos_widget.delay_sec)
        self.delay_slider.valueChanged.connect(self.update_delay_slider_value)
        self.delay_textbox = QLineEdit(str(self.delay_slider.value()))
        self.delay_textbox.setFixedWidth(50)
        self.delay_textbox.textEdited.connect(self.update_delay_textbox_value)
        delay_layout.addWidget(QLabel(f"Camera delay(sec)"))
        delay_layout.addWidget(self.delay_slider)
        delay_layout.addWidget(self.delay_textbox)
        self.view_tab_layout.addLayout(delay_layout)
        #--- camera delay slider ---
        

        #--- camera size slider ---
        for i in self.cam_indexes:
            slider_layout = QHBoxLayout()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(320, 1920)
            slider.setValue(640)
            slider.valueChanged.connect(self.update_width_slider_values)
            slider_layout.addWidget(QLabel(f"Camera {i}"))
            slider_layout.addWidget(slider)
            self.width_sliders.append(slider)

            self.view_tab_layout.addLayout(slider_layout)
        #--- camera size slider ---


        #--- display cross ---
        self.cross_layout = QHBoxLayout()
        self.cross_checkbox = QCheckBox("View cross")
        self.cross_checkbox.setChecked(False)
        self.cross_checkbox.toggled.connect(self.update_cross_checkbox)
        
        self.cross_layout.addWidget(self.cross_checkbox)
        self.view_tab_layout.addLayout(self.cross_layout)
        #--- display cross ---

        #--- cross height slider ---
        for i in self.cam_indexes:
            slider_layout = QHBoxLayout()

            slider_x = QSlider(Qt.Orientation.Horizontal)
            slider_x.setRange(0, 100)
            slider_x.setValue(50)
            slider_x.valueChanged.connect(self.update_cross_x_slider_values)

            slider_y = QSlider(Qt.Orientation.Horizontal)
            slider_y.setRange(0, 100)
            slider_y.setValue(50)
            slider_y.valueChanged.connect(self.update_cross_y_slider_values)

            slider_layout.addWidget(QLabel(f"Camera {i}"))
            slider_layout.addWidget(slider_x)
            slider_layout.addWidget(slider_y)
            self.cross_x_sliders.append(slider_x)
            self.cross_y_sliders.append(slider_y)

            self.view_tab_layout.addLayout(slider_layout)
        #--- cross height slider ---




        record_start_button = QPushButton("Start")
        record_start_button.clicked.connect(self.start_record)
        self.record_tab_layout.addWidget(record_start_button)
        record_stop_button = QPushButton("Stop")
        record_stop_button.clicked.connect(self.stop_record)
        self.record_tab_layout.addWidget(record_stop_button)

        self.camera_tab_layout.addStretch()
        self.view_tab_layout.addStretch()
        self.record_tab_layout.addStretch()


    def update_camera_num(self):
        self.cam_indexes = [int(camera_combo.currentText()) for camera_combo in self.camera_idx_combos]
        camera_num = int(self.camera_num_combo.currentText())
        if len(self.cam_indexes) > camera_num:
            self.cam_indexes = self.cam_indexes[:camera_num]
        
        elif len(self.cam_indexes) < camera_num:
            for i in self.available_cameras:
                if int(i) not in self.cam_indexes:
                    self.cam_indexes.append(int(i))

                if len(self.cam_indexes) >= camera_num:
                    break
            
            self.cam_indexes = self.cam_indexes + ([0] * (camera_num - len(self.cam_indexes)))

        self.videos_widget.set_cam_indexes(self.cam_indexes)
        self.videos_widget.reload()
        self.reload()

    def update_delay_slider_value(self, delay_sec):
        self.delay_textbox.setText(str(delay_sec))
        self.videos_widget.update_delay(int(delay_sec))

    def update_cross_x_slider_values(self):
        if len(self.cross_x_sliders) != len(self.videos_widget.video_widgets):
            print("[!] update cross x slider value: out of range")
            return
        cross_x = [cross_slider.value() for cross_slider in self.cross_x_sliders]
        for i, video_widget in enumerate(self.videos_widget.video_widgets):
            video_widget.set_cross_x(cross_x[i])
        
    def update_cross_y_slider_values(self):
        if len(self.cross_y_sliders) != len(self.videos_widget.video_widgets):
            print(f"[!] update cross y slider value: out of range")
            return
        cross_y = [cross_slider.value() for cross_slider in self.cross_y_sliders]
        for i, video_widget in enumerate(self.videos_widget.video_widgets):
            video_widget.set_cross_y(cross_y[i])
        
        
    def update_delay_textbox_value(self):
        if self.delay_textbox.text() != "":
            self.delay_slider.setValue(int(self.delay_textbox.text()))

    def update_width_slider_values(self):
        if len(self.width_sliders) != len(self.videos_widget.video_widgets):
            print("[!] update width slider value: out of range")
            return
        widths = [width_slider.value() for width_slider in self.width_sliders]
        for i, video_widget in enumerate(self.videos_widget.video_widgets):
            video_widget.set_video_widget_width(widths[i])

    def update_cross_checkbox(self):
        for video_widget in self.videos_widget.video_widgets:
            video_widget.set_cross_flag(self.cross_checkbox.isChecked())

    def start_record(self):
        self.videos_widget.start_record()
    
    def stop_record(self):
        self.videos_widget.stop_record()


if __name__ == "__main__":
    try:
        os.mkdir(tmp_dir)
    except:
        pass

    
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec_())