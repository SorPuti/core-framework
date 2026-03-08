"""
Exemplo de uso do Sistema de Logger Global do Stride

Execute com:
    python examples/logger_example.py

Ou configure via variáveis de ambiente:
    LOG_LEVEL=DEBUG python examples/logger_example.py
"""

import sys
import os

# Adiciona o path do projeto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ============================================================================
# MÉTODO 1: Importe e use diretamente (recomendado)
# ============================================================================

from strider import logger

# Configure o nível de log (opcional - StrideApp faz isso automaticamente)
from strider import configure_logging
configure_logging(level="DEBUG")

# Use diretamente - funciona em qualquer lugar do seu código
print("=== Usando logger exportado ===")
logger.debug("Esta é uma mensagem de DEBUG - nunca mais some!")
logger.info("Esta é uma mensagem de INFO")
logger.warning("Esta é uma mensagem de WARNING")
logger.error("Esta é uma mensagem de ERROR")
logger.critical("Esta é uma mensagem de CRITICAL")


# ============================================================================
# MÉTODO 2: Crie um logger com nome customizado
# ============================================================================

from strider.logger import get_logger

print("\n=== Usando get_logger ===")
my_logger = get_logger("meu_modulo")

my_logger.info("Log do meu_modulo")
my_logger.debug("Debug específico do meu_modulo - também funciona!")


# ============================================================================
# MÉTODO 3: Formato JSON (para ELK, Datadog, etc)
# ============================================================================

print("\n=== Formato JSON ===")
configure_logging(level="INFO", json_format=True, force=True)

logger.info("Log em formato JSON")


# ============================================================================
# MÉTODO 4: Configuração via Settings
# ============================================================================

print("\n=== Configuração via Settings (exemplo) ===")
print("""
# src/settings.py
from strider.config import Settings, configure

class AppSettings(Settings):
    log_level: str = "DEBUG"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_json: bool = False  # True para JSON

settings = configure(settings_class=AppSettings)
# O logging é configurado automaticamente!
""")

print("\n✓ Exemplo concluído!")
