import io
import random

import cv2
import m3u8


def get_video_ss(video, ss_path: str = None) -> str:
    if isinstance(video, io.BytesIO):
        video_data = video.getvalue()
        video = cv2.VideoCapture()
        video.open("dummy.mp4", cv2.CAP_FFMPEG)
        video.write(video_data)
        video.set(cv2.CAP_PROP_POS_FRAMES, 0)
    else:
        video = cv2.VideoCapture(video)

    total_frames = round(video.get(cv2.CAP_PROP_FRAME_COUNT))

    random_frame = random.randint(0, total_frames - 1)
    video.set(cv2.CAP_PROP_POS_FRAMES, random_frame)
    ret, frame = video.read()

    ss_path = ss_path or f"frame_{random_frame}.jpg"
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


def resolutions_from_m3u8(m3u8_url: str) -> dict:
    playlist = m3u8.load(m3u8_url)
    video_urls = {
        str(playlist.stream_info.resolution[1]) + "p": playlist.uri
        if playlist.uri.startswith("http")
        else playlist.base_uri + playlist.uri
        for playlist in playlist.playlists
    }
    return video_urls
