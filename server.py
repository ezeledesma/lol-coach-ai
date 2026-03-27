from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from typing import Optional, List, Dict, Any
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.responses import JSONResponse, RedirectResponse
import shutil
import os
import uuid
from video_utils import extract_frames_from_report
from coach_ai import detect_champions_async, generate_coach_report_async, ask_coach_ai

app = FastAPI(title="LoL AI Coach Web")

analysis_tasks = {}

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

class ChampionsPayload(BaseModel):
    task_id: str
    file_id: str
    api_key: Optional[str] = None
    champions: List[Dict[str, Any]]

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse(url="https://ddragon.leagueoflegends.com/cdn/14.4.1/img/profileicon/29.png")

@app.post("/api/detect-champions")
async def api_detect_champions(
    background_tasks: BackgroundTasks, 
    video: UploadFile = File(...),
    api_key: Optional[str] = Form(None)
):
    valid_exts = (".mp4", ".mkv", ".webm", ".mov", ".jpg", ".jpeg", ".png", ".webp")
    if not video.filename.lower().endswith(valid_exts):
        raise HTTPException(status_code=400, detail="El archivo no es un formato válido de video o imagen soportado")
        
    task_id = str(uuid.uuid4())
    temp_path = f"temp_{task_id}_{video.filename}"
    analysis_tasks[task_id] = {
        "status": "Guardando multimedia localmente en el servidor...",
        "progress": 30,
        "state": "PROCESSING_CHAMPIONS",
        "result": None,
        "error": None,
        "local_temp_path": temp_path
    }
        
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error guardando el video.")

    def run_detection():
        try:
            def update_progress(msg, pct):
                analysis_tasks[task_id]["status"] = msg
                # La fase 1 llega como máximo al 50% del total visual
                # Convertimos el 0-100% de la fase 1 a 30-50% real progresivo
                real_pct = 30 + (pct * 0.2)
                analysis_tasks[task_id]["progress"] = real_pct
                
            res = detect_champions_async(temp_path, update_progress, custom_api_key=api_key)
            
            # Estado para requerir interacción del usuario
            analysis_tasks[task_id]["state"] = "REQUIRES_CONFIRMATION"
            analysis_tasks[task_id]["result"] = res # Contiene file_id y champions
            
        except Exception as e:
            analysis_tasks[task_id]["error"] = str(e)
            analysis_tasks[task_id]["state"] = "FAILED"
            if os.path.exists(temp_path):
                os.remove(temp_path)

    background_tasks.add_task(run_detection)
    return JSONResponse(content={"task_id": task_id})

@app.post("/api/generate-report")
async def api_generate_report(payload: ChampionsPayload, background_tasks: BackgroundTasks):
    task_id = payload.task_id
    if task_id not in analysis_tasks:
        analysis_tasks[task_id] = {
            "status": "Iniciando análisis profundo...", "progress": 50, "state": "PROCESSING_REPORT", "result": None, "error": None
        }
    else:
        analysis_tasks[task_id]["state"] = "PROCESSING_REPORT"
        analysis_tasks[task_id]["progress"] = 50

    def run_report():
        try:
            def update_progress(msg, pct):
                analysis_tasks[task_id]["status"] = msg
                # La fase 2 va del 50% al 100% real
                real_pct = 50 + (pct * 0.5)
                analysis_tasks[task_id]["progress"] = real_pct
                
            final_report = generate_coach_report_async(
                file_id=payload.file_id, 
                confirmed_champs=payload.champions, 
                progress_callback=update_progress, 
                custom_api_key=payload.api_key
            )
            
            analysis_tasks[task_id]["state"] = "DONE"
            analysis_tasks[task_id]["result"] = final_report
            analysis_tasks[task_id]["file_id"] = payload.file_id
            analysis_tasks[task_id]["champ_data"] = payload.champions
            
            # Phase 3: Extract frames if it's a video
            temp_path = analysis_tasks[task_id].get("local_temp_path")
            if temp_path and os.path.exists(temp_path):
                extract_frames_from_report(temp_path, task_id, final_report)
            
        except Exception as e:
            analysis_tasks[task_id]["error"] = str(e)
            analysis_tasks[task_id]["state"] = "FAILED"
        finally:
            temp_path = analysis_tasks.get(task_id, {}).get("local_temp_path")
            if temp_path and os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass

    background_tasks.add_task(run_report)
    return JSONResponse(content={"status": "scheduled"})

@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    if task_id not in analysis_tasks:
        raise HTTPException(status_code=404, detail="Tarea no encontrada o expirada.")
    return JSONResponse(content=analysis_tasks[task_id])

class ChatPayload(BaseModel):
    task_id: str
    message: str
    api_key: Optional[str] = None

@app.post("/api/chat")
async def api_chat(payload: ChatPayload):
    task_id = payload.task_id
    if task_id not in analysis_tasks:
        raise HTTPException(status_code=404, detail="La sesión de análisis ha caducado o no existe.")
        
    task_data = analysis_tasks[task_id]
    if task_data.get("state") != "DONE":
        raise HTTPException(status_code=400, detail="Debes esperar a que termine el análisis antes de chatear.")
        
    try:
        file_id = task_data.get("file_id")
        if not file_id:
            raise HTTPException(status_code=500, detail="Error interno: file_id perdido")
            
        response_text = ask_coach_ai(file_id, task_data, payload.message, payload.api_key)
        return JSONResponse(content={"reply": response_text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
