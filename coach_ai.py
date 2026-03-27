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
    team: Literal["Aliado", "Enemigo"] = Field(description="Si el campeón figura en la misma lista del scoreboard que el jugador POV, es 'Aliado'. Si figura del otro lado, es 'Enemigo'. Ignora los colores de la barra de vida.")
    role: Literal["Top", "Jungle", "Mid", "ADC", "Support"] = Field(description="Rol en la partida.")
    is_pov: bool = Field(description="Indica si este campeón es el jugador cuya pantalla se está grabando.")

class ChampionList(BaseModel):
    champions: list[ChampionEntity] = Field(description="Lista de EXACTAMENTE 10 campeones encontrados en el scoreboard o durante la partida.")
    pov_side: Literal["Blue", "Red"] = Field(description="Indica de qué lado del Tabulador se muestran los ALIADOS. 'Blue' si están a la izquierda del tabulador, 'Red' si están a la derecha.")

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
    player_profile_tag: str = Field(description="Etiqueta breve del perfil de estilo de juego (Ej: 'Agresivo', 'Teamfighter', 'Pasivo', 'Rotador').")
    player_profile_reason: str = Field(description="Breve justificación del perfil asignado basada en el comportamiento o la situación analizada.")

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
    2. Su equipo (Aliado o Enemigo). REGLA ESTRICTA: Busca al jugador de cuya perspectiva vemos el juego (POV). TODOS los campeones que están en la MISMA MITAD (Izquierda o Derecha) de la tabla de puntuaciones (Tab) que el jugador POV son sus 'Aliados'. Los de la otra mitad son 'Enemigos'. NUNCA asumas aliados basándote en que un equipo sea rojo o azul, guíate 100% por qué bloque ocupa el jugador principal en la tabla.
    3. Llena `pov_side` con 'Blue' si los aliados del POV ocupan el bloque izquierdo de la tabla (Tab), o 'Red' si ocupan el bloque derecho.
    4. Su rol en la partida.
    5. Quién es el jugador POV (la cámara que graba).
    
    No analices jugadas, solo extrae el JSON estrictamente.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[video_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ChampionList,
                temperature=0.0
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
        media_file = client.files.get(name=file_id)
        if media_file.state != "ACTIVE":
            raise RuntimeError("El archivo no está activo en Gemini.")
    except Exception as e:
        raise RuntimeError(f"No se pudo recuperar el archivo subido de Gemini: {e}")

    update_progress(f"[*] El Coach Challenger está redactando la crítica detallada ({media_file.mime_type})...", 70)
    
    is_video = media_file.mime_type.startswith("video")
    
    if is_video:
        media_rules = """
        === REGLAS MULTIMEDIA (VIDEO/CLIP) ===
        - Si esto es un CLIP CORTO (solo dura unos segundos o ~3 minutos), ENFÓCATE EN LAS MECÁNICAS E INTERCAMBIOS (micro game). NO hables de macro, oleadas o roamings globales. En clips cortos el `momentum_graph` DEBE estar VACÍO [].
        - Si esto es una PARTIDA COMPLETA, ENFÓCATE EN EL MACRO, TEMPO y TOMA DE OBJETIVOS y completa el `momentum_graph` normalmente.
        """
    else:
        media_rules = """
        === REGLAS MULTIMEDIA (IMAGEN/CAPTURA) ===
        - La persona te ha mandado una CAPTURA DE PANTALLA. NO HAY VIDEO.
        - Si es una PANTALLA DE CARGA (Loading Screen): Detalla minuciosamente las Win Conditions completas, qué campeones deben presionar en early, y qué ITEMS clave necesita cada uno.
        - Si es una captura In-Game de un Frame: Describe qué debería estar haciendo el jugador en ese instante y critica su posición.
        - IMPORTANTE: En el campo `momentum_graph`, retorna obligatoriamente una lista vacía `[]`.
        """

    prompt = f"""
    Eres un Coach de League of Legends de nivel Challenger. Analiza esta grabación o imagen desde la perspectiva del jugador.
    
    === CONTEXTO DE LA PARTIDA (CONFIRMADO POR EL USUARIO) ===
    Utiliza esta lista de campeones como VERDAD ABSOLUTA del estado de los equipos. No falles.
    Campeones en partida:
    {json.dumps(confirmed_champs, indent=2, ensure_ascii=False)}
    ========================================================

    {media_rules}

    === REGLAS ESTRICTAS MACRO/MICRO ===
    1. TIMESTAMPS: Taguea con `[MM:SS]` o tiempos aproximados si aplica. (Si es imagen estática, usa `[Fase de Líneas]` o algo acorde).
    2. ROLES: Juzga si cumplen su rol base según la lista.
    3. ITEMS Y BUILD: Evalúa de manera estricta las compras u opciones lógicas de itemización (ej. anti-curaciones si aplica).
    4. WIN CONDITION: Llena `game_plan` argumentando cómo debería jugar.
    5. PERFIL: Llena `player_profile_tag` y `player_profile_reason` resumiendo psicológicamente su estilo (Ej: Agresivo, Arriesgado, Powerfarmer). Si es una imagen, infiere cómo DEBERÍA actuar.

    === TIEMPO Y MOMENTUM ===
    Presta estricta atención a las reglas de si es un clip, un juego o una imagen para definir el `momentum_graph`.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[media_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CoachReport,
                temperature=0.0
            )
        )
        update_progress("[*] Análisis y redacción completados con éxito.", 100)
        # Importante: No borramos el archivo de Google así puede reusarse en el Chat Interactivo (Fase 3).
        return json.loads(response.text)

    except Exception as e:
        print(f"[!] Error durante el reporte final: {e}")
        # En caso de error, liberamos almacenamiento preventivamente
        try: client.files.delete(name=media_file.name)
        except: pass
        raise RuntimeError(f"Error generando reporte: {e}")

def ask_coach_ai(file_id: str, task_context: dict, message: str, custom_api_key: str | None = None) -> str:
    client = _get_client(custom_api_key, lambda m, p: None)
    try:
        media_file = client.files.get(name=file_id)
        
        system_context = f"""
        Sos un Coach Challenger de LoL interactuando en vivo mediante un chat.
        Ya hiciste el siguiente reporte inicial sobre el video/imagen que el usuario te subió:
        {json.dumps(task_context.get("result", {}), ensure_ascii=False)}
        
        Campeones en la partida:
        {json.dumps(task_context.get("champ_data", []), ensure_ascii=False)}
        
        Responde a la nueva duda/pregunta que tiene el usuario, fijándote de nuevo en el video/imagen adjunto. 
        Habla como un Coach experimentado que da tips muy directo, amigable y usando jerga de LoL.
        Respuesta en formato Markdown, clara y sin excederte de longitud (máx 3 párrafos).
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[system_context, media_file, message]
        )
        return response.text
    except Exception as e:
        raise RuntimeError(f"Error respondiendo en el chat: {e}")

