"""
Sistema de Logger Global - Stride Framework

Uso simples - importe e use diretamente:
    from strider import logger
    
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

Ou crie um logger com nome customizado:
    from strider.logger import get_logger
    
    logger = get_logger("my_module")
    logger.info("Hello from my_module")

Configuração automática via Settings:
    class Settings:
        log_level: str = "DEBUG"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
        log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        log_json: bool = False

O logger é configurado UMA VEZ na inicialização e funciona globalmente.
Nunca mais use logging.getLogger() diretamente.
"""

import logging
import logging.handlers
import sys
from typing import Any, Literal

# Logger principal exportado
__all__ = ["logger", "get_logger", "configure_logging", "Logger"]

# Tipo para type hints
Logger = logging.Logger


class _LoggerManager:
    """
    Gerenciador interno de loggers.
    
    Responsável por:
    - Configurar o root logger uma vez
    - Criar loggers nomeados quando solicitado
    - Garantir que todos os loggers respeitem a configuração global
    """
    
    _configured: bool = False
    _log_level: int = logging.INFO
    _log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    _log_json: bool = False
    _handlers: list[logging.Handler] = []
    
    @classmethod
    def configure(
        cls,
        level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
        log_format: str | None = None,
        json_format: bool = False,
        force: bool = False,
    ) -> None:
        """
        Configura o sistema de logging global.
        
        Args:
            level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_format: Formato customizado (None usa padrão)
            json_format: Se True, usa formato JSON estruturado
            force: Se True, reconfigura mesmo se já estiver configurado
        """
        if cls._configured and not force:
            return
        
        # Converte level string para int
        level_int = getattr(logging, level.upper(), logging.INFO)
        cls._log_level = level_int
        cls._log_json = json_format
        
        # Define formato
        if log_format:
            cls._log_format = log_format
        elif json_format:
            cls._log_format = '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
        else:
            cls._log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        # Configura root logger - SEMPRE atualiza o nível
        root_logger = logging.getLogger()
        root_logger.setLevel(level_int)

        # Verifica se já existem handlers (ex: Uvicorn já configurou)
        has_existing_handlers = len(root_logger.handlers) > 0

        if force:
            # Remove todos os handlers se estiver forçando reconfiguração
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            has_existing_handlers = False

        # Só adiciona nosso handler se não houver handlers existentes
        # Isso preserva a configuração do Uvicorn quando ele já configurou
        if not has_existing_handlers:
            # Cria handler para stdout
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(level_int)

            # Formatter
            formatter = logging.Formatter(cls._log_format, datefmt="%Y-%m-%d %H:%M:%S")
            handler.setFormatter(formatter)

            # Adiciona handler ao root
            root_logger.addHandler(handler)
            cls._handlers = [handler]

        # Configura loggers do Uvicorn para o mesmo nível
        # Isso garante que as logs de request apareçam
        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_access = logging.getLogger("uvicorn.access")
        uvicorn_error = logging.getLogger("uvicorn.error")

        uvicorn_logger.setLevel(level_int)
        uvicorn_access.setLevel(level_int)
        uvicorn_error.setLevel(level_int)

        # Garante que os handlers existentes tenham o nível correto
        if has_existing_handlers:
            for handler in root_logger.handlers:
                handler.setLevel(level_int)

        # CRÍTICO: O Uvicorn pode ter propagate=False nos loggers de access/error
        # Se não tiver handlers próprios, as logs somem. Precisamos garantir que
        # esses loggers tenham handlers se estiverem com propagate=False
        for uvicorn_logger_instance in [uvicorn_logger, uvicorn_access, uvicorn_error]:
            # Ajusta nível dos handlers existentes
            for handler in uvicorn_logger_instance.handlers:
                handler.setLevel(level_int)

            # Se o logger tem propagate=False e não tem handlers, adiciona um
            if not uvicorn_logger_instance.propagate and not uvicorn_logger_instance.handlers:
                handler = logging.StreamHandler(sys.stdout)
                handler.setLevel(level_int)
                handler.setFormatter(logging.Formatter('%(levelname)s:     %(message)s'))
                uvicorn_logger_instance.addHandler(handler)

        # Configura loggers de bibliotecas comuns para não poluir
        # quando o nível é DEBUG
        if level_int <= logging.DEBUG:
            logging.getLogger("asyncio").setLevel(logging.WARNING)
            logging.getLogger("urllib3").setLevel(logging.WARNING)
            logging.getLogger("requests").setLevel(logging.WARNING)
            logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
            logging.getLogger("aiokafka").setLevel(logging.WARNING)
        
        cls._configured = True
        
        # Log que o sistema foi configurado (apenas se não estiver reconfigurando)
        if not force:
            config_logger = logging.getLogger("strider.logger")
            config_logger.debug("Logging configured: level=%s, json=%s", level, json_format)
    
    @classmethod
    def get_logger(cls, name: str = "strider") -> logging.Logger:
        """
        Retorna um logger configurado com o nome especificado.
        
        Args:
            name: Nome do logger (aparece nos logs)
            
        Returns:
            Logger configurado
        """
        # Garante que está configurado
        if not cls._configured:
            cls.configure()
        
        logger = logging.getLogger(name)
        return logger
    
    @classmethod
    def is_configured(cls) -> bool:
        """Verifica se o logging já foi configurado."""
        return cls._configured
    
    @classmethod
    def get_level(cls) -> int:
        """Retorna o nível de log atual."""
        return cls._log_level


def configure_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    log_format: str | None = None,
    json_format: bool = False,
    force: bool = False,
) -> None:
    """
    Configura o sistema de logging global.
    
    Normalmente chamado automaticamente pela StrideApp.
    Você raramente precisa chamar isso manualmente.
    
    Args:
        level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Formato customizado de log
        json_format: Se True, usa formato JSON
        force: Se True, força reconfiguração
        
    Exemplo:
        configure_logging(level="DEBUG", json_format=True)
    """
    _LoggerManager.configure(
        level=level,
        log_format=log_format,
        json_format=json_format,
        force=force,
    )


def get_logger(name: str = "strider") -> logging.Logger:
    """
    Retorna um logger configurado com o nome especificado.
    
    Use isso quando quiser um logger com nome customizado para
    identificar a origem dos logs.
    
    Args:
        name: Nome do logger (ex: "myapp.models", "api.views")
        
    Returns:
        Logger configurado e pronto para usar
        
    Exemplo:
        from strider.logger import get_logger
        
        logger = get_logger("my_module")
        logger.info("Processando dados...")
        # Saída: 2024-01-15 10:30:45 - my_module - INFO - Processando dados...
    """
    return _LoggerManager.get_logger(name)


# ============================================================================
# LOGGER GLOBAL - IMPORTE E USE DIRETAMENTE
# ============================================================================

# Logger padrão exportado - importe assim:
#   from strider import logger
#   logger.info("Hello!")
# Inicialmente cria um logger sem configurar - configuração acontece no primeiro uso
# ou quando StrideApp inicia
logger: logging.Logger = logging.getLogger("strider")


# ============================================================================
# Integração com Settings (chamado automaticamente)
# ============================================================================

def _configure_from_settings() -> None:
    """
    Configura o logging automaticamente a partir das Settings.
    Chamado automaticamente pela StrideApp no startup.
    """
    try:
        from strider.config import get_settings
        
        settings = get_settings()
        
        # Só configura se ainda não estiver configurado
        if not _LoggerManager.is_configured():
            configure_logging(
                level=settings.log_level,  # type: ignore
                log_format=settings.log_format if hasattr(settings, "log_format") else None,
                json_format=getattr(settings, "log_json", False),
            )
    except Exception:
        # Se não conseguir carregar settings, usa defaults
        if not _LoggerManager.is_configured():
            configure_logging()


# Conveniência: alias para compatibilidade
def setup_logging(*args: Any, **kwargs: Any) -> None:
    """Alias para configure_logging."""
    configure_logging(*args, **kwargs)
