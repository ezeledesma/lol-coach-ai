import sys
import os
from coach_ai import analyze_video

def main():
    if len(sys.argv) < 2:
        print("Uso: python main.py <ruta_al_video.mp4>")
        print("Ejemplo: python main.py mi_partida.mp4")
        sys.exit(1)
        
    video_path = sys.argv[1]
    
    if not os.path.exists(video_path):
        print(f"Error: El archivo de video '{video_path}' no existe en esta ruta.")
        sys.exit(1)
        
    # Verificar que el entorno esté configurado
    if not os.environ.get("GEMINI_API_KEY") and not os.path.exists(".env"):
        print("Advertencia: No se encontró la GEMINI_API_KEY ni un archivo .env configurado.")
        
    analyze_video(video_path)

if __name__ == "__main__":
    main()
