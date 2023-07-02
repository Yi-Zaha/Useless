import random

import cv2


def get_video_ss(video_path: str, ss_path: str = None) -> str:
    video = cv2.VideoCapture(video_path)
    total_frames = round(video.get(cv2.CAP_PROP_FRAME_COUNT))

    random_frame = random.randint(0, total_frames - 1)
    video.set(cv2.CAP_PROP_POS_FRAMES, random_frame)
    ret, frame = video.read()

    ss_path = ss_path or f"{video_path.split('.')[0]}_{random_frame}.jpg"
    cv2.imwrite(ss_path, frame)

    video.release()
    return ss_path


def get_video_duration(path: str) -> int:
    video = cv2.VideoCapture(path)
    fps = video.get(cv2.CAP_PROP_FPS)
    total_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = int(total_frames / fps)
    video.release()
    return duration


def get_video_frames(path: str) -> int:
    video = cv2.VideoCapture(path)
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    video.release()
    return total_frames
