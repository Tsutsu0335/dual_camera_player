import threading
import time
import cv2
import ffmpeg
import numpy as np

class CameraStream:
    def __init__(self, cam_index, delay_sec=0, delay_sec_max=45, fps=30, height=1080, width=1980):
        self.cam_index = cam_index
        self.delay_sec = delay_sec
        self.delay_sec_max = delay_sec_max
        self.fps = fps
        self.height = height
        self.width = width

        self.now_fps = 0

        self.frame = None
        self.running = True
        self.recording = False
        self.process = None
        self.writer = None
        self.buffer = []
        self.buf_lock = threading.Lock()
        self.frame_lock = threading.Lock()
        self.process_lock = threading.Lock()

    def start(self):
        self.cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        print(f"camera{self.cam_index}:  fps: {self.cap.get(cv2.CAP_PROP_FPS)}, width: {self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)}, height: {self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")
        
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue
            timestamp = time.time()

            with self.buf_lock:
                self.buffer = [buf for buf in self.buffer if (timestamp - buf[0]) <= self.delay_sec_max]
                self.buffer.append((timestamp, frame))
                
                delayed_frame = None
                for (t, f) in self.buffer:
                    if timestamp - t >= self.delay_sec:
                        delayed_frame = f
                    else:
                        break
                
            with self.frame_lock:    
                self.frame = delayed_frame
                
            with self.process_lock:
                if self.recording and self.process is not None:
                    self.process.stdin.write(delayed_frame.astype(np.uint8).tobytes())


    def start_recording(self, filename):
        if self.recording:
            return 
        
        self.process = (
            ffmpeg.input('pipe:', format='rawvideo', pix_fmt='bgr24', 
                         s='{}x{}'.format(self.width, self.height), use_wallclock_as_timestamps=1)
                  .output(filename, fps_mode='vfr', **{'b:v': '3000k'})
                  .overwrite_output()
                  .run_async(pipe_stdin=True)
        )
        
        self.recording = True

    def stop_recording(self):
        if not self.recording:
            return
        
        self.recording = False
        with self.process_lock:    
            self.process.stdin.close()
            self.process.wait()
            self.process = None

    def get_frame(self):
        with self.frame_lock:
            return self.frame if self.frame is not None else None

    def set_delay(self, delay_sec):
        with self.buf_lock:
            self.delay_sec = min(max(0, delay_sec), self.delay_sec_max - 1)
    
    def release(self):
        self.running = False
        self.thread.join()
        self.cap.release()
        
def detect_available_cameras(max_index=10):
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(str(i))
            cap.release()
    return available if available else None

def main():
    camera_thread = CameraStream(0)
    camera_thread.start()

    frame_count = 0
    start_time = time.time()

    while True:
        frame = camera_thread.get_frame()
        if frame is not None:
            cv2.imshow("Camera Thread", frame)
            frame_count += 1

            if frame_count >= 100:
                elapsed_time = time.time() - start_time
                fps = frame_count / elapsed_time
                print(f"Measured FPS: {fps:.2f}")
                frame_count = 0
                start_time = time.time()

        key = cv2.waitKey(1)
        if  key & 0xFF == ord('q'):
            break

        
        if key & 0xFF == ord('a'):
            camera_thread.set_delay(5)

        if key & 0xFF == ord('s'):
            camera_thread.set_delay(0)

        if key & 0xFF == ord('w'):
            camera_thread.set_delay(40)

    camera_thread.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
