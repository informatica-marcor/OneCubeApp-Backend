import logging
import sys
from pathlib import Path
from app.core.config import settings

# Definir la ruta de los logs
LOG_DIR = Path(settings.root) / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"


def setup_logging():
    # 1. Crear el formato de los mensajes
    # Incluimos: tiempo, nivel, nombre del módulo y el mensaje
    log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 2. Handler para la consola (StreamHandler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)

    # 3. Handler para archivo (FileHandler)
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(log_formatter)

    # 4. Configuración del logger raíz (Root Logger)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Cambiar a DEBUG para ver todo
    
    # Evitar duplicados si se llama varias veces
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    # Opcional: Silenciar logs ruidosos de librerías externas
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return root_logger