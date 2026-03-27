import os
import time
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

class ScoreInfo(BaseModel):
    score: int = Field(description="Puntuación del 1 al 10")
    reason: str = Field(description="Breve razón de la puntuación")

class MomentumPoint(BaseModel):
    time_minute: int = Field(description="Minuto o segundo de la partida aprox.")
    momentum_score: int = Field(description="Puntuación del momentum competitivo de 1 a 10 (1=Perdiendo abismalmente, 5=Igualados, 10=Snowball/Dominando)")
    reason: str = Field(description="Suceso clave que provocó este nivel de ventaja o desventaja (Ej. 'Robo de Barón', 'Cazaron al ADC aliado', 'Quadrakill en top').")

class CoachReport(BaseModel):
    good_things: list[str] = Field(description="Pros. DEBE iniciar OBLIGATORIAMENTE con el timestamp del video [MM:SS].")
    mistakes: list[str] = Field(description="Errores críticos. DEBE iniciar OBLIGATORIAMENTE con el timestamp del video [MM:SS].")
    advice: list[str] = Field(description="Consejos accionables para mejorar, INCLUYENDO crítica detallada de su compra de Items.")
    game_plan: str = Field(description="Análisis de la Win Condition o rol en TF basado en TODAS las composiciones (Ej: Flanquear, Front to Back, Splitpush, etc).")
    momentum_graph: list[MomentumPoint] = Field(description="Lista temporal para graficar la evolución del momentum percibido de la partida.")
    mechanics_score: ScoreInfo = Field(description="Puntuación en mecánicas")
    map_awareness_score: ScoreInfo = Field(description="Puntuación en consciencia del mapa y visión")
    positioning_score: ScoreInfo = Field(description="Puntuación en posicionamiento en peleas o línea")

# --------------------------------------------------------------------------

def analyze_video_json(video_path: str, progress_callback=None, custom_api_key: str | None = None) -> dict:
    def update_progress(msg, pct):
        if progress_callback:
            progress_callback(msg, pct)
        print(msg)

    update_progress(f"[*] Iniciando análisis de coaching en backend: {video_path}", 32)
    
    try:
        # Soportamos un modo público donde el propio usuario que subió el video ingresó su propia Key
        if custom_api_key and len(custom_api_key.strip()) > 10:
            client = genai.Client(api_key=custom_api_key.strip())
            update_progress("[*] Autenticado con API Key proporcionada por el invitado.", 35)
        else:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("No se proporcionó API KEY manual ni se encontró clave GEMINI_API_KEY en el .env")
            client = genai.Client(api_key=api_key)
            update_progress("[*] Autenticado con API Key del servidor (.env local).", 35)
            
    except Exception as e:
        raise RuntimeError(f"Fallo en la autenticación de la API Key: {e}")

    update_progress("[*] Subiendo video a los servidores de Google Gemini (esto puede tardar unos minutos)...", 40)
    try:
        video_file = client.files.upload(file=video_path)
    except Exception as e:
        raise RuntimeError(f"Error al subir el video: {e}")
        
    update_progress(f"[*] Video subido con éxito. ID: {video_file.name}", 55)
    
    update_progress("[*] Gemini está escaneando los fotogramas y tu inventario... (puede tardar minutos)", 60)
    time.sleep(5) # Delay crítico para permitir la propagación global del archivo subido en Google
    
    retries = 0
    while True:
        try:
            file_info = client.files.get(name=video_file.name)
            if file_info.state == "ACTIVE":
                update_progress("[*] Procesamiento visual completado. Fotogramas analizados.", 80)
                break
            elif file_info.state == "FAILED":
                raise RuntimeError("El procesamiento del video falló internamente en Google.")
            
            time.sleep(5)
            retries = 0 # Reset de reintentos si responde bien pero sigue procesando
            
        except Exception as api_err:
            # Capturamos 403/404 transitorios por delay de red en la infraestructura de Google
            retries += 1
            if retries > 5:
                raise RuntimeError(f"Falla de permisos/existencia en Google tras múltiples intentos: {api_err}")
            time.sleep(3)

    update_progress("[*] El Coach Challenger está evaluando el Win Condition, Oleadas y redactando JSON...", 85)
    
    prompt = """
    Eres un Coach de League of Legends de nivel Challenger. Analiza esta grabación de VOD desde la perspectiva única del jugador.

    === RECONOCIMIENTO VISUAL DE CAMPEONES (CRÍTICO) ===
    - TU JUGADOR (POV) tiene la barra de vida VERDE o AMARILLA (daltonismo).
    - ALIADOS: Barras AZULES o nombres amigables sobre sus cabezas. ENEMIGOS: Barras ROJAS.
    - OBLIGATORIO: Analiza la pantalla del TAB (Scoreboard) detenidamente. Memoriza qué campeones están de tu lado y cuáles en el equipo rival. ESTO EVITARÁ CONFUSIONES.
    - CUIDADO con Viego y Sylas. Ignora sus modelos visuales cuando roban aspectos/habilidades. Guíate ESTRICTAMENTE por la lista de campeones del TAB y los íconos del minimapa para saber a qué equipo pertenecen realmente.

    === REGLAS ESTRICTAS MACRO/MICRO ===
    1. TIMESTAMPS: Toda jugada en Puntos Fuertes/Errores DEBE iniciar con `[MM:SS]`.
    2. WAVE MANAGEMENT Y TEMPO: Juzga cuándo el jugador debió Freezear (para denegar o por riesgo de gank) o Pushear. Critica si arriesga perder Tempo o morir por una placa de torre innecesaria en lugar de backear a su 'Powerspike'.
    3. ROLES Y JUNGLE TRACKING: Penaliza si no cumple su rol base (Mid no rota cruzando el río, Support roba XP o no wardea, Top no hace split-push con ventaja). Si es Jugla, critica si pierde eficiencia o farmeo ('Full Clear') arriesgándose a un robo cruzado ('Invade') por forzar ganks malos.
    4. DRAGONES Y OBJETIVOS: Critica forzar peleas estúpidas ignorando si el buff de ese tipo de Dragón específico beneficiaba o no a la composición aliada/enemiga.
    5. ITEMS Y SCOREBOARD (TAB): Si presiona TAB o abre la Tienda, haz auditoría letal: si el enemigo acumula Resistencia Mágica, DEBEN llevar Báculo del Vacío/Criptoflora y NO puro Rabadon; Si hay curaciones brutales sin cortacuras (Llamamiento/Morello), destrózalos en el review.
    6. WIN CONDITION: Llena el campo `game_plan` detallando cómo debería jugar LAS PELEAS considerando las comps: Front-to-Back, Dive a la backline veloz, Flanquear, Hacer Peel forzado al ADC, o ceder split push.

    === TIEMPO Y MOMENTUM (GRÁFICO) ===
    Observa el flujo de la partida y extrae al menos 4 a 6 eventos (MomentumPoint). Indica el minuto, la puntuación de la ventaja (1 a 10) y OBLIGATORIAMENTE el campo 'reason' detallando el suceso exacto o la pelea que causó esa fluctuación en la ventaja de la gráfica.
    
    Medir 1 al 10 en puntuaciones estáticas. Sé realista y muy directo. Todo en Español.
    """
    
    try:
        # Forzar que el modelo de GenAI nos retorne en formato JSON basado en el modelo Pydantic
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[video_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CoachReport,
                temperature=0.2
            )
        )
        
        update_progress("[*] Análisis y redacción del Coach completados con éxito.", 100)
        client.files.delete(name=video_file.name)
        
        # Como es un modelo schema, text es un string de JSON
        return json.loads(response.text)

    except Exception as e:
        print(f"[!] Error durante la generación: {e}")
        # Limpiar en caso de falla
        client.files.delete(name=video_file.name)
        raise RuntimeError(f"Error en la IA: {e}")
