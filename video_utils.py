import os
import cv2
import re

def extract_frames_from_report(temp_path: str, task_id: str, report: dict):
    if not os.path.exists(temp_path) or not temp_path.lower().endswith((".mp4", ".mkv", ".webm", ".mov")):
        return # Si no es video o no existe, no hacemos nada

    # 1. Recolectar textos donde buscar timestamps
    texts_to_search = []
    texts_to_search.extend(report.get("good_things", []))
    texts_to_search.extend(report.get("mistakes", []))
    texts_to_search.extend(report.get("advice", []))
    
    # regex para atrapar [MM:SS] o [HH:MM:SS] o [M:SS]
    pattern = r'\[(\d{1,2}:\d{2}(?::\d{2})?)\]'
    
    unique_timestamps_str = set()
    for text in texts_to_search:
        matches = re.findall(pattern, text)
        for m in matches:
            unique_timestamps_str.add(m)
            
    if not unique_timestamps_str:
        return # No hay timestamps

    # Preparar el directorio
    frames_dir = os.path.join("static", "frames")
    os.makedirs(frames_dir, exist_ok=True)
    
    try:
        cap = cv2.VideoCapture(temp_path)
        if not cap.isOpened():
            print(f"[!] OpenCV no pudo abrir el video {temp_path}")
            return
            
        for time_str in unique_timestamps_str:
            # Parsear time_str a segundos
            parts = time_str.split(":")
            seconds = 0
            if len(parts) == 2:
                seconds = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                
            # Mover cabezal
            cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
            ret, frame = cap.read()
            if ret:
                # Normalizar el time_str para el nombre del archivo: 03:45 -> 03_45
                safe_time_str = time_str.replace(":", "_")
                filename = f"{task_id}_{safe_time_str}.jpg"
                filepath = os.path.join(frames_dir, filename)
                
                # Opcional: Redimensionar para no ocupar tanto espacio (720p máx de ancho)
                h, w = frame.shape[:2]
                if w > 1280:
                    ratio = 1280 / w
                    frame = cv2.resize(frame, (1280, int(h * ratio)))

                cv2.imwrite(filepath, frame)
                print(f"[*] Guardado frame: {filepath}")
    except Exception as e:
        print(f"[!] Error extrayendo frames con cv2: {e}")
    finally:
        if 'cap' in locals() and cap is not None:
            cap.release()
