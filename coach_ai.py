import os
import time
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import Literal
from dotenv import load_dotenv

load_dotenv()

class ChampionEntity(BaseModel):
    name: str = Field(description="Nombre literal del campeón en inglés (Ej: 'Ahri', 'MissFortune'). Debe ser el nombre interno usado en el juego (sin espacios de preferencia para la API de imágenes).")
    team: Literal["Aliado", "Enemigo"] = Field(description="Equipo al que pertenece (Aliado si su barra es azul o verde, Enemigo si es roja).")
    role: Literal["Top", "Jungle", "Mid", "ADC", "Support"] = Field(description="Rol en la partida.")
    is_pov: bool = Field(description="Indica si este campeón es el jugador cuya pantalla se está grabando.")

class ChampionList(BaseModel):
    champions: list[ChampionEntity] = Field(description="Lista de EXACTAMENTE 10 campeones encontrados en el scoreboard o durante la partida.")

class ScoreInfo(BaseModel):
    score: int = Field(description="Puntuación del 1 al 10")
    reason: str = Field(description="Breve razón de la puntuación")

class MomentumPoint(BaseModel):
    time_minute: int = Field(description="Minuto o segundo de la partida aprox.")
    momentum_score: int = Field(description="Puntuación del momentum competitivo de 1 a 10 (1=Perdiendo abismalmente, 5=Igualados, 10=Snowball/Dominando)")
    reason: str = Field(description="Suceso clave que provocó este nivel de ventaja o desventaja (Ej. 'Robo de Barón', 'Quadrakill en top').")

class CoachReport(BaseModel):
    good_things: list[str] = Field(description="Pros. DEBE iniciar OBLIGATORIAMENTE con el timestamp del video [MM:SS].")
    mistakes: list[str] = Field(description="Errores críticos. DEBE iniciar OBLIGATORIAMENTE con el timestamp del video [MM:SS].")
    advice: list[str] = Field(description="Consejos accionables para mejorar, INCLUYENDO crítica detallada de su compra de Items.")
    game_plan: str = Field(description="Análisis de la Win Condition o rol en TF basado en TODAS las composiciones (Ej: Flanquear, Front to Back, Splitpush, etc).")
    momentum_graph: list[MomentumPoint] = Field(description="Lista temporal para graficar la evolución del momentum percibido de la partida.")
    mechanics_score: ScoreInfo = Field(description="Puntuación en mecánicas")
    map_awareness_score: ScoreInfo = Field(description="Puntuación en consciencia del mapa y visión")
    positioning_score: ScoreInfo = Field(description="Puntuación en posicionamiento en peleas o línea")

def _get_client(custom_api_key, update_progress):
    if custom_api_key and len(custom_api_key.strip()) > 10:
        client = genai.Client(api_key=custom_api_key.strip())
        update_progress("[*] Autenticado con API Key proporcionada por el invitado.", 35)
    else:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("No se proporcionó API KEY manual ni se encontró clave GEMINI_API_KEY en el .env")
        client = genai.Client(api_key=api_key)
        update_progress("[*] Autenticado con API Key del servidor (.env local).", 35)
    return client

def detect_champions_async(video_path: str, progress_callback=None, custom_api_key: str | None = None) -> dict:
    def update_progress(msg, pct):
        if progress_callback: progress_callback(msg, pct)
        print(msg)

    update_progress(f"[*] Iniciando Fase 1: Extracción de Campeones - {video_path}", 32)
    client = _get_client(custom_api_key, update_progress)
    
    update_progress("[*] Subiendo video a Gemini (esto puede tardar unos minutos)...", 40)
    try:
        video_file = client.files.upload(file=video_path)
    except Exception as e:
        raise RuntimeError(f"Error al subir el video: {e}")
        
    update_progress(f"[*] Video subido. ID: {video_file.name}", 50)
    
    update_progress("[*] Gemini está escaneando los fotogramas para extraer campeones...", 60)
    time.sleep(5)
    
    retries = 0
    while True:
        try:
            file_info = client.files.get(name=video_file.name)
            if file_info.state == "ACTIVE":
                update_progress("[*] Procesamiento visual completado. Solicitando entidades...", 80)
                break
            elif file_info.state == "FAILED":
                raise RuntimeError("El procesamiento del video falló internamente en Google.")
            time.sleep(5)
            retries = 0
        except Exception as api_err:
            retries += 1
            if retries > 5:
                raise RuntimeError(f"Falla de permisos/existencia en Google tras múltiples intentos: {api_err}")
            time.sleep(3)

    update_progress("[*] La IA está deduciendo los campeones de ambos equipos...", 85)
    
    prompt = """
    Analiza esta grabación de League of Legends. Solo necesito que extraigas a los 10 campeones que participan en la partida.
    Identifica:
    1. El nombre del campeón.
    2. Su equipo (Aliado o Enemigo) prestando atención a los colores (Aliado=Azul/Verde, Enemigo=Rojo).
    3. Su rol en la partida.
    4. Quién es el jugador POV (la cámara que graba).
    
    No analices jugadas, solo extrae el JSON estrictamente.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[video_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ChampionList,
                temperature=0.1
            )
        )
        update_progress("[*] Campeones extraídos exitosamente. Esperando validación del usuario.", 100)
        champs_json = json.loads(response.text)
        return {"file_id": video_file.name, "champions": champs_json["champions"]}
    except Exception as e:
        print(f"[!] Error extrayendo campeones: {e}")
        client.files.delete(name=video_file.name)
        raise RuntimeError(f"Error en detección de campeones: {e}")

def generate_coach_report_async(file_id: str, confirmed_champs: list, progress_callback=None, custom_api_key: str | None = None) -> dict:
    def update_progress(msg, pct):
        if progress_callback: progress_callback(msg, pct)
        print(msg)

    update_progress("[*] Iniciando Fase 2: Análisis profundo con campeones confirmados...", 50)
    client = _get_client(custom_api_key, update_progress)
    
    try:
        video_file = client.files.get(name=file_id)
        if video_file.state != "ACTIVE":
            raise RuntimeError("El archivo no está activo en Gemini.")
    except Exception as e:
        raise RuntimeError(f"No se pudo recuperar el archivo subido de Gemini: {e}")

    update_progress("[*] El Coach Challenger está redactando la crítica detallada...", 70)
    
    prompt = f"""
    Eres un Coach de League of Legends de nivel Challenger. Analiza esta grabación desde la perspectiva del jugador.
    
    === CONTEXTO DE LA PARTIDA (CONFIRMADO POR EL USUARIO) ===
    Utiliza esta lista de campeones como VERDAD ABSOLUTA del estado de los equipos. No falles. No te fíes al 100% solo de lo visual si esto dice algo distinto (caso Viego o Sylas).
    Campeones en partida:
    {json.dumps(confirmed_champs, indent=2, ensure_ascii=False)}
    ========================================================

    === REGLAS ESTRICTAS MACRO/MICRO ===
    1. TIMESTAMPS: Toda jugada en Puntos Fuertes/Errores DEBE iniciar con `[MM:SS]`.
    2. WAVE MANAGEMENT Y TEMPO: Juzga cuándo el jugador debió Freezear o Pushear. Critica si arriesga perder Tempo.
    3. ROLES Y JUNGLE TRACKING: Penaliza si no cumple su rol base según la lista confirmada.
    4. DRAGONES Y OBJETIVOS: Critica forzar peleas estúpidas ignorando recompensas.
    5. ITEMS Y SCOREBOARD: Si presiona TAB o abre la Tienda, haz auditoría letal: si el enemigo acumula MR, DEBEN llevar Báculo del Vacío/Criptoflora.
    6. WIN CONDITION: Llena el campo `game_plan` detallando cómo debería jugar LAS PELEAS considerando las comps exactas proporcionadas.

    === TIEMPO Y MOMENTUM ===
    Extrae al menos 4 a 6 eventos (MomentumPoint), con el minuto y el cambio de ventaja (1=Perdiendo abismalmente, 10=Dominando).
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[video_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CoachReport,
                temperature=0.2
            )
        )
        update_progress("[*] Análisis y redacción completados con éxito.", 100)
        client.files.delete(name=video_file.name)
        return json.loads(response.text)

    except Exception as e:
        print(f"[!] Error durante el reporte final: {e}")
        client.files.delete(name=video_file.name)
        raise RuntimeError(f"Error generando reporte: {e}")
