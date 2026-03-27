from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from typing import Optional
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
import shutil
import os
import uuid
from coach_ai import analyze_video_json

app = FastAPI(title="LoL AI Coach Web")

# Diccionario global para sincronizar el progreso entre procesos
analysis_tasks = {}

# Crear el directorio 'static' si no existe
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.post("/api/analyze")
async def api_analyze_video(
    background_tasks: BackgroundTasks, 
    video: UploadFile = File(...),
    api_key: Optional[str] = Form(None)
):
    if not video.filename.lower().endswith((".mp4", ".mkv", ".webm", ".mov")):
        raise HTTPException(status_code=400, detail="El archivo debe ser un formato de video (.mp4, .mkv, .webm, .mov)")
        
    task_id = str(uuid.uuid4())
    analysis_tasks[task_id] = {
        "status": "Guardando video localmente en el servidor...",
        "progress": 30, # El 0 a 30% lo cubre el frontend subiendo el archivo
        "result": None,
        "error": None,
        "done": False
    }
        
    temp_path = f"temp_{task_id}_{video.filename}"
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
            
        print(f"[*] Recibido archivo: {video.filename}, iniciando tarea en segundo plano ID: {task_id}")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error de servidor procesando el video guardado.")

    def run_ai():
        try:
            def update_progress(msg, pct):
                analysis_tasks[task_id]["status"] = msg
                analysis_tasks[task_id]["progress"] = pct
                
            report_data = analyze_video_json(temp_path, update_progress, custom_api_key=api_key)
            
            analysis_tasks[task_id]["result"] = report_data
            analysis_tasks[task_id]["done"] = True
            
        except Exception as e:
            print(f"Error esperado o inesperado en IA: {e}")
            analysis_tasks[task_id]["error"] = str(e)
            analysis_tasks[task_id]["done"] = True
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Añadimos la ejecución pesada de IA de fondo, y devolvemos rápidamente el task ID
    background_tasks.add_task(run_ai)
    return JSONResponse(content={"task_id": task_id})

@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    if task_id not in analysis_tasks:
        raise HTTPException(status_code=404, detail="Tarea no encontrada o expirada.")
    return JSONResponse(content=analysis_tasks[task_id])

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("Iniciando tu servidor Web Coach...")
    print("Abre esta dirección en tu navegador: http://127.0.0.1:8000/static/index.html")
    print("="*50 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
