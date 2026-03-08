# Sistema de Logger Global

O Stride Framework possui um sistema de logging global simples e poderoso. Você nunca mais precisa usar `logging.getLogger()` diretamente.

## Uso Básico

### Importe e Use Diretamente

```python
from strider import logger

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")
```

### Logger com Nome Customizado

```python
from strider.logger import get_logger

logger = get_logger("my_module")
logger.info("Hello from my_module")
# Saída: 2024-01-15 10:30:45 - my_module - INFO - Hello from my_module
```

## Configuração

### Via Settings (Recomendado)

```python
from strider.config import Settings, configure

class AppSettings(Settings):
    log_level: str = "DEBUG"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_json: bool = False  # True para formato JSON

configure(settings_class=AppSettings)
```

### Via Variáveis de Ambiente

```bash
# .env
LOG_LEVEL=DEBUG
LOG_FORMAT="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_JSON=false
```

## Por que DEBUG não sume mais?

O problema com `logging.getLogger()` é que loggers filhos nem sempre herdam o nível do root logger. Nosso sistema garante que:

1. **Configuração única**: O logging é configurado UMA VEZ no startup
2. **Nível global**: Todos os loggers respeitam o nível configurado
3. **Propagation**: Loggers filhos automaticamente usam o nível do root

## Uso em Projetos

### Exporte para uso em projetos externos

```python
# No __init__.py do seu projeto
from strider import logger, get_logger

__all__ = ["logger", "get_logger"]
```

### Em qualquer arquivo do seu projeto

```python
from strider import logger

def minha_funcao():
    logger.debug("Entrando na função")
    # ... código ...
    logger.info("Processo concluído")
```

## Formato JSON

Para logs estruturados (útil para ELK, Datadog, etc):

```python
configure_logging(level="INFO", json_format=True)
```

Saída:
```json
{"timestamp": "2024-01-15 10:30:45", "level": "INFO", "name": "strider", "message": "Hello"}
```

## API

### `logger`

Logger padrão exportado. Use: `from strider import logger`

### `get_logger(name: str) -> Logger`

Retorna um logger com nome customizado.

```python
from strider.logger import get_logger
logger = get_logger("myapp.models")
```

### `configure_logging()`

Configura o sistema de logging (normalmente chamado automaticamente).

```python
from strider.logger import configure_logging

configure_logging(
    level="DEBUG",
    log_format="%(asctime)s - %(levelname)s - %(message)s",
    json_format=False,
    force=True  # Reconfigurar se já estiver configurado
)
```

## Compatibilidade

O sistema é compatível com código existente que usa `logging.getLogger()`:

```python
import logging

# Isso ainda funciona porque configuramos o root logger
old_logger = logging.getLogger("old_module")
old_logger.info("Funciona!")
```

## Diferenças do logging padrão

| Aspecto | logging padrão | Stride Logger |
|---------|---------------|---------------|
| Configuração | Cada módulo faz a própria | Centralizada |
| Nível DEBUG | Frequentemente "some" | Sempre visível quando configurado |
| Setup | Múltiplas chamadas | Uma chamada no startup |
| Uso | `logging.getLogger(__name__)` | `from strider import logger` |
