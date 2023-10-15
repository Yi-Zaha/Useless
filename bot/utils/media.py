import io
import json
import os
import random

import cv2
from bot.utils.functions import run_cmd

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

    ss_path = ss_path or f"{os.path.splitext(ss_path)[0][:51]}_{random_frame}.jpg"
    cv2.imwrite(ss_path, frame)

    video.release()
    return ss_path

async def get_metadata(file):
    media_info = await get_media_info(file)
    data = {}

    info = media_info[0]

    format_type = info.get("Format")
    if format_type in ["GIF", "PNG"]:
        data["height"] = media_info[1]["Height"]
        data["width"] = media_info[1]["Width"]
        data["bitrate"] = media_info[1].get("BitRate", 320)
    else:
        if info.get("AudioCount"):
            data["title"] = info.get("Title", file)
            data["performer"] = info.get("Performer", "")

        if info.get("VideoCount"):
            data["height"] = int(float(media_info[1].get("Height", 720))
            data["width"] = int(float(media_info[1].get("Width", 1280))
            data["bitrate"] = int(media_info[1].get("BitRate", 320))
            data["frame_rate"] = round(float(media_info[1].get("FrameRat", "0.0")))

    data["duration"] = int(float(info.get("Duration", 0))
    return data

async def get_media_info(file, output_type="JSON"):
    out, err = await run_cmd(f'mediainfo --Output="{output_type}" "{str(file)}"')
    if err:
        raise ValueError(f"Invalid media: {err}")
    
    if output_type.lower() == "json":
        return json.loads(out)["media"]["track"]
    return out
