import cv2 as cv
import time
import os
from datetime import datetime

# 카메라(리모트 RTSP) 열기
url = "rtsp://210.99.70.120:1935/live/cctv026.stream"
# 요청하는 시스템에 따라 backend를 명시하면 더 안정적
cap = cv.VideoCapture(url, cv.CAP_FFMPEG)

# 간단한 재시도 로직
if not cap.isOpened():
    print("Stream not opened, retrying...")
    for _ in range(5):
        time.sleep(1)
        cap.open(url, cv.CAP_FFMPEG)
        if cap.isOpened():
            break

if not cap.isOpened():
    print("Error: Unable to open RTSP stream:", url)
    exit(1)

# 해상도 및 FPS 가져오기 (값이 없으면 기본값 사용)
width = int(cap.get(cv.CAP_PROP_FRAME_WIDTH) or 640)
height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT) or 480)
fps_val = cap.get(cv.CAP_PROP_FPS)
fps = int(fps_val) if fps_val and fps_val > 0 else 20
# sanitize reported fps: some RTSP streams report timebase-like values (e.g. 90000)
# which cause FFmpeg/VideoWriter to fail. Clamp to a sane recording FPS.
if fps > 120:
    print(f"Warning: camera reported high fps ({fps}), clamping to 30 for recording")
    fps = 30
print(f"Opened stream: {url} - {width}x{height} @ {fps} FPS")
# create window and mouse callback for button
window_name = "OpenCV Video Recorder"
cv.namedWindow(window_name, cv.WINDOW_NORMAL)

# UI / 기능 변수
invert_colors = False
# 회전 상태 (0, 90, 180, 270)
rotation_deg = 0
# 버튼 위치: 오른쪽 위
btn_w, btn_h = 110, 30
btn_x, btn_y = max(10, width - btn_w - 10), 10
button_rect = (btn_x, btn_y, btn_w, btn_h)

# 배경 추정용 누적 이미지
background_accum = None
last_bg_save_time = 0

def on_mouse(event, x, y, flags, param):
    global invert_colors
    bx, by, bw, bh = button_rect
    if event == cv.EVENT_LBUTTONUP:
        if bx <= x <= bx + bw and by <= y <= by + bh:
            invert_colors = not invert_colors

cv.setMouseCallback(window_name, on_mouse)

recording = False
start_time = 0
out = None
writer_error_reported = False

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # 현재 시간
    current_time = time.time()

    # 배경 누적 업데이트 (원본 프레임 사용)
    if background_accum is None:
        background_accum = frame.astype('float32')
    else:
        # alpha 작게 설정하면 천천히 적응
        cv.accumulateWeighted(frame.astype('float32'), background_accum, 0.01)

    # FPS 계산
    fps_text = f"FPS: {fps}"

    # 녹화 중이면
    if recording:
        elapsed = int(current_time - start_time)

        # 빨간 점 표시
        cv.circle(frame, (30,30), 10, (0,0,255), -1)

        # 녹화 표시
        cv.putText(frame, "RECORDING", (50,35),
                    cv.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)

        # 녹화 시간 표시
        cv.putText(frame, f"Time: {elapsed}s", (10,70),
                    cv.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

        # 실제로 VideoWriter가 열려 있는지 확인하고 기록
        if out is not None and hasattr(out, 'isOpened') and out.isOpened():
            out.write(frame)
        else:
            if not writer_error_reported:
                print("Warning: VideoWriter is not opened. Frames will not be saved.")
                writer_error_reported = True

    # 회전된 디스플레이 프레임 생성 (원본 프레임은 배경/녹화용으로 유지)
    def rotate_frame(img, deg):
        if deg == 0:
            return img
        if deg == 90:
            return cv.rotate(img, cv.ROTATE_90_CLOCKWISE)
        if deg == 180:
            return cv.rotate(img, cv.ROTATE_180)
        if deg == 270:
            return cv.rotate(img, cv.ROTATE_90_COUNTERCLOCKWISE)
        return img

    disp = rotate_frame(frame, rotation_deg)

    # 버튼 위치는 디스플레이 크기에 맞춰 매 프레임 갱신
    disp_h, disp_w = disp.shape[:2]
    bx = max(10, disp_w - btn_w - 10)
    by = 10
    button_rect = (bx, by, btn_w, btn_h)

    # 버튼 배경 및 텍스트
    cv.rectangle(disp, (bx, by), (bx + btn_w, by + btn_h), (50, 50, 50), -1)
    btn_label = "Invert" if not invert_colors else "Normal"
    cv.putText(disp, btn_label, (bx + 8, by + 20),
                cv.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

    # 배경 저장 알림
    if time.time() - last_bg_save_time < 2:
        cv.putText(disp, "Background saved", (10, 100),
                    cv.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)

    # PREVIEW MODE 텍스트 (디스플레이에 그림) - 녹화 중에는 표시하지 않음
    if not recording:
        cv.putText(disp, "PREVIEW MODE", (10,25),
                    cv.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

    # 색상 반전 적용 (디스플레이용)
    if invert_colors:
        disp = cv.bitwise_not(disp)

    # FPS 표시 (디스플레이 크기 기준)
    cv.putText(disp, fps_text, (10, disp_h-10),
                cv.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)

    cv.imshow(window_name, disp)

    # use waitKeyEx to capture special keys (F1 등)
    key = cv.waitKeyEx(1)

    # ESC 종료
    if key == 27:
        break

    # Space → 녹화 모드 전환
    if key == 32:
        recording = not recording

        if recording:
            start_time = time.time()

            # 파일 이름 자동 생성 (.mp4)
            filename = datetime.now().strftime("record_%Y%m%d_%H%M%S.mp4")

            # 실제 프레임 크기 사용(카메라에서 읽은 프레임 기반)
            fh, fw = frame.shape[:2]
            print(f"Starting recording. cap reported {width}x{height} @ {fps}fps, frame size {fw}x{fh}")

            # MP4 저장을 위해 mp4v 코덱 시도
            fourcc = cv.VideoWriter_fourcc(*'mp4v')
            out = cv.VideoWriter(filename, fourcc, fps, (fw, fh))
            if not out.isOpened():
                print("VideoWriter(mp4v) failed to open. Trying XVID/.avi fallback...")
                # .avi + XVID fallback
                filename = filename.replace('.mp4', '.avi')
                fourcc = cv.VideoWriter_fourcc(*'XVID')
                out = cv.VideoWriter(filename, fourcc, fps, (fw, fh))
                if not out.isOpened():
                    print("Fallback VideoWriter(XVID) also failed. Frames will not be saved.")
                else:
                    print("Recording Start (fallback):", filename)
                    writer_error_reported = False
            else:
                print("Recording Start:", filename)
                writer_error_reported = False

        else:
            if out:
                out.release()
            print("Recording Stop")

    # 1 / 2 회전 기능 (1 = 왼쪽으로 90도, 2 = 오른쪽으로 90도)
    if key == ord('1'):
        rotation_deg = (rotation_deg - 90) % 360
        print(f"Rotate left -> {rotation_deg} deg")
    if key == ord('2'):
        rotation_deg = (rotation_deg + 90) % 360
        print(f"Rotate right -> {rotation_deg} deg")

    # 'b' 키 → 배경 이미지 저장 (원본 orientation)
    if key == ord('b'):
        if background_accum is not None:
            os.makedirs('Saved', exist_ok=True)
            bg_img = cv.convertScaleAbs(background_accum)
            bg_filename = os.path.join('Saved', datetime.now().strftime("background_%Y%m%d_%H%M%S.png"))
            cv.imwrite(bg_filename, bg_img)
            print("Background saved:", bg_filename)
            last_bg_save_time = time.time()

cap.release()
if out:
    out.release()
cv.destroyAllWindows()
