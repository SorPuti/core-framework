"""
Sistema de DateTime unificado em UTC.

NUNCA use datetime diretamente no SDK - use sempre este módulo.

Este módulo garante:
- Todos os timestamps são em UTC
- Sincronização entre serviços
- Configuração centralizada de timezone
- Compatibilidade com diferentes fusos

Uso simplificado (recomendado):
    from core import timezone
    
    # Sempre retorna UTC
    current = timezone.now()
    today = timezone.today()
    
    # Converter para timezone do usuário
    user_time = timezone.localtime(current, "America/Sao_Paulo")
    
    # Verificações
    if timezone.is_past(some_date):
        ...

Uso alternativo:
    from core.datetime import DateTime, UTC
    
    dt = DateTime(2024, 1, 15, 10, 30, tzinfo=UTC)
"""

from __future__ import annotations

import functools
from datetime import (
    datetime as _datetime,
    date as _date,
    time as _time,
    timedelta,
    timezone as _timezone,
)
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass


# =============================================================================
# Timezone Constants
# =============================================================================

UTC = _timezone.utc


# =============================================================================
# Configuração Global
# =============================================================================

class DateTimeConfig:
    """
    Configuração global de DateTime.
    
    Permite customizar o comportamento do sistema de datas.
    """
    
    def __init__(self) -> None:
        self._default_timezone: _timezone = UTC
        self._auto_now_timezone: _timezone = UTC
        self._use_aware_datetimes: bool = True
        self._date_format: str = "%Y-%m-%d"
        self._time_format: str = "%H:%M:%S"
        self._datetime_format: str = "%Y-%m-%dT%H:%M:%S%z"
    
    @property
    def default_timezone(self) -> _timezone:
        """Timezone padrão para novos datetimes."""
        return self._default_timezone
    
    @default_timezone.setter
    def default_timezone(self, tz: _timezone | str) -> None:
        if isinstance(tz, str):
            tz = get_timezone(tz)
        self._default_timezone = tz
    
    @property
    def auto_now_timezone(self) -> _timezone:
        """Timezone para campos auto_now e auto_now_add."""
        return self._auto_now_timezone
    
    @auto_now_timezone.setter
    def auto_now_timezone(self, tz: _timezone | str) -> None:
        if isinstance(tz, str):
            tz = get_timezone(tz)
        self._auto_now_timezone = tz
    
    @property
    def use_aware_datetimes(self) -> bool:
        """Se deve sempre criar datetimes com timezone."""
        return self._use_aware_datetimes
    
    @use_aware_datetimes.setter
    def use_aware_datetimes(self, value: bool) -> None:
        self._use_aware_datetimes = value
    
    def configure(
        self,
        default_timezone: _timezone | str | None = None,
        auto_now_timezone: _timezone | str | None = None,
        use_aware_datetimes: bool | None = None,
        date_format: str | None = None,
        time_format: str | None = None,
        datetime_format: str | None = None,
    ) -> None:
        """
        Configura o sistema de DateTime.
        
        Args:
            default_timezone: Timezone padrão
            auto_now_timezone: Timezone para auto_now
            use_aware_datetimes: Se deve usar datetimes aware
            date_format: Formato de data
            time_format: Formato de hora
            datetime_format: Formato de datetime
        """
        if default_timezone is not None:
            self.default_timezone = default_timezone
        if auto_now_timezone is not None:
            self.auto_now_timezone = auto_now_timezone
        if use_aware_datetimes is not None:
            self._use_aware_datetimes = use_aware_datetimes
        if date_format is not None:
            self._date_format = date_format
        if time_format is not None:
            self._time_format = time_format
        if datetime_format is not None:
            self._datetime_format = datetime_format


# Instância global
_config = DateTimeConfig()


def get_datetime_config() -> DateTimeConfig:
    """Retorna a configuração global de DateTime."""
    return _config


def configure_datetime(**kwargs) -> None:
    """
    Configura o sistema de DateTime.
    
    Exemplo:
        configure_datetime(
            default_timezone="America/Sao_Paulo",
            use_aware_datetimes=True,
        )
    """
    _config.configure(**kwargs)


# =============================================================================
# Timezone Utilities
# =============================================================================

# Cache de timezones
_timezone_cache: dict[str, _timezone] = {
    "UTC": UTC,
    "utc": UTC,
}


def get_timezone(name: str) -> _timezone:
    """
    Obtém um timezone por nome.
    
    Args:
        name: Nome do timezone (ex: "America/Sao_Paulo", "UTC", "+03:00")
        
    Returns:
        Objeto timezone
        
    Exemplo:
        tz = get_timezone("America/Sao_Paulo")
        tz = get_timezone("UTC")
        tz = get_timezone("+03:00")
    """
    if name in _timezone_cache:
        return _timezone_cache[name]
    
    # Tenta offset fixo (+03:00, -05:00)
    if name.startswith(("+", "-")):
        try:
            sign = 1 if name[0] == "+" else -1
            parts = name[1:].split(":")
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            offset = timedelta(hours=hours, minutes=minutes) * sign
            tz = _timezone(offset, name)
            _timezone_cache[name] = tz
            return tz
        except (ValueError, IndexError):
            pass
    
    # Tenta usar zoneinfo (Python 3.9+)
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(name)
        _timezone_cache[name] = tz
        return tz
    except ImportError:
        pass
    except Exception:
        pass
    
    # Tenta usar pytz se disponível
    try:
        import pytz
        tz = pytz.timezone(name)
        _timezone_cache[name] = tz
        return tz
    except ImportError:
        pass
    except Exception:
        pass
    
    raise ValueError(f"Unknown timezone: {name}. Install 'pytz' or use Python 3.9+ for full timezone support.")


# =============================================================================
# DateTime Class (wrapper)
# =============================================================================

class DateTime(_datetime):
    """
    DateTime customizado que sempre opera em UTC por padrão.
    
    Substitui datetime.datetime em todo o SDK.
    
    Características:
    - Sempre aware (com timezone)
    - UTC por padrão
    - Métodos de conversão integrados
    - Compatível com Pydantic
    
    Uso:
        # Criar datetime UTC
        dt = DateTime(2024, 1, 15, 10, 30)
        
        # Criar com timezone específico
        dt = DateTime(2024, 1, 15, 10, 30, tzinfo=get_timezone("America/Sao_Paulo"))
        
        # Converter para outro timezone
        dt_sp = dt.to_timezone("America/Sao_Paulo")
    """
    
    # =========================================================================
    # Pydantic Support
    # =========================================================================
    
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """
        Define como Pydantic deve validar e serializar DateTime.
        
        Aceita:
        - DateTime
        - datetime
        - string ISO 8601
        - int/float (timestamp)
        """
        from pydantic_core import core_schema
        
        def validate_datetime(value: Any) -> "DateTime":
            if isinstance(value, DateTime):
                return value
            if isinstance(value, _datetime):
                return DateTime.from_datetime(value)
            if isinstance(value, str):
                return DateTime.from_iso(value)
            if isinstance(value, (int, float)):
                return DateTime.from_timestamp(value)
            raise ValueError(f"Cannot convert {type(value)} to DateTime")
        
        def serialize_datetime(value: "DateTime") -> str:
            return value.isoformat()
        
        return core_schema.no_info_plain_validator_function(
            validate_datetime,
            serialization=core_schema.plain_serializer_function_ser_schema(
                serialize_datetime,
                info_arg=False,
                return_schema=core_schema.str_schema(),
            ),
        )
    
    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """Define o schema JSON para OpenAPI."""
        return {
            "type": "string",
            "format": "date-time",
            "description": "ISO 8601 datetime string",
            "example": "2024-01-15T10:30:00+00:00",
        }
    
    def __new__(
        cls,
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
        tzinfo: _timezone | None = None,
        *,
        fold: int = 0,
    ) -> "DateTime":
        # Se não tem timezone e config diz para usar aware, usa UTC
        if tzinfo is None and _config.use_aware_datetimes:
            tzinfo = _config.default_timezone
        
        instance = super().__new__(
            cls, year, month, day, hour, minute, second, microsecond, tzinfo, fold=fold
        )
        return instance
    
    def to_timezone(self, tz: _timezone | str) -> "DateTime":
        """
        Converte para outro timezone.
        
        Args:
            tz: Timezone de destino
            
        Returns:
            Novo DateTime no timezone especificado
        """
        if isinstance(tz, str):
            tz = get_timezone(tz)
        
        converted = self.astimezone(tz)
        return DateTime(
            converted.year,
            converted.month,
            converted.day,
            converted.hour,
            converted.minute,
            converted.second,
            converted.microsecond,
            tzinfo=converted.tzinfo,
        )
    
    def to_utc(self) -> "DateTime":
        """Converte para UTC."""
        return self.to_timezone(UTC)
    
    def to_iso(self) -> str:
        """Retorna string ISO 8601."""
        return self.isoformat()
    
    def to_timestamp(self) -> float:
        """Retorna Unix timestamp."""
        return self.timestamp()
    
    @classmethod
    def from_timestamp(cls, ts: float, tz: _timezone | str | None = None) -> "DateTime":
        """
        Cria DateTime a partir de Unix timestamp.
        
        Args:
            ts: Unix timestamp
            tz: Timezone (padrão: UTC)
        """
        if tz is None:
            tz = UTC
        elif isinstance(tz, str):
            tz = get_timezone(tz)
        
        dt = _datetime.fromtimestamp(ts, tz=tz)
        return cls(
            dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second, dt.microsecond,
            tzinfo=dt.tzinfo,
        )
    
    @classmethod
    def from_iso(cls, iso_string: str) -> "DateTime":
        """
        Cria DateTime a partir de string ISO 8601.
        
        Args:
            iso_string: String ISO (ex: "2024-01-15T10:30:00Z")
        """
        dt = _datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return cls(
            dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second, dt.microsecond,
            tzinfo=dt.tzinfo or UTC,
        )
    
    @classmethod
    def from_datetime(cls, dt: _datetime) -> "DateTime":
        """Converte datetime padrão para DateTime."""
        return cls(
            dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second, dt.microsecond,
            tzinfo=dt.tzinfo or (_config.default_timezone if _config.use_aware_datetimes else None),
        )


# Aliases para compatibilidade
Date = _date
Time = _time
TimeDelta = timedelta
Timezone = _timezone


# =============================================================================
# Funções de Conveniência
# =============================================================================

def now(tz: _timezone | str | None = None) -> DateTime:
    """
    Retorna o datetime atual.
    
    Args:
        tz: Timezone (padrão: UTC)
        
    Returns:
        DateTime atual no timezone especificado
        
    Exemplo:
        current = now()  # UTC
        current_sp = now("America/Sao_Paulo")
    """
    if tz is None:
        tz = _config.auto_now_timezone
    elif isinstance(tz, str):
        tz = get_timezone(tz)
    
    dt = _datetime.now(tz)
    return DateTime.from_datetime(dt)


def utcnow() -> DateTime:
    """
    Retorna o datetime atual em UTC.
    
    Returns:
        DateTime atual em UTC
    """
    return now(UTC)


def today(tz: _timezone | str | None = None) -> Date:
    """
    Retorna a data atual.
    
    Args:
        tz: Timezone para determinar a data
        
    Returns:
        Data atual
    """
    return now(tz).date()


def make_aware(
    dt: _datetime,
    tz: _timezone | str | None = None,
) -> DateTime:
    """
    Torna um datetime naive em aware.
    
    Args:
        dt: Datetime naive
        tz: Timezone a aplicar (padrão: UTC)
        
    Returns:
        DateTime aware
    """
    if dt.tzinfo is not None:
        return DateTime.from_datetime(dt)
    
    if tz is None:
        tz = _config.default_timezone
    elif isinstance(tz, str):
        tz = get_timezone(tz)
    
    return DateTime(
        dt.year, dt.month, dt.day,
        dt.hour, dt.minute, dt.second, dt.microsecond,
        tzinfo=tz,
    )


def make_naive(dt: _datetime, tz: _timezone | str | None = None) -> _datetime:
    """
    Remove timezone de um datetime.
    
    Args:
        dt: Datetime aware
        tz: Timezone para converter antes de remover
        
    Returns:
        Datetime naive
    """
    if dt.tzinfo is None:
        return dt
    
    if tz is not None:
        if isinstance(tz, str):
            tz = get_timezone(tz)
        dt = dt.astimezone(tz)
    
    return dt.replace(tzinfo=None)


def to_timezone(dt: _datetime, tz: _timezone | str) -> DateTime:
    """
    Converte datetime para outro timezone.
    
    Args:
        dt: Datetime a converter
        tz: Timezone de destino
        
    Returns:
        DateTime no novo timezone
    """
    if isinstance(tz, str):
        tz = get_timezone(tz)
    
    if dt.tzinfo is None:
        dt = make_aware(dt)
    
    converted = dt.astimezone(tz)
    return DateTime.from_datetime(converted)


def is_aware(dt: _datetime) -> bool:
    """Verifica se datetime tem timezone."""
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def is_naive(dt: _datetime) -> bool:
    """Verifica se datetime não tem timezone."""
    return not is_aware(dt)


# =============================================================================
# Formatação
# =============================================================================

def format_datetime(
    dt: _datetime,
    fmt: str | None = None,
    tz: _timezone | str | None = None,
) -> str:
    """
    Formata datetime como string.
    
    Args:
        dt: Datetime a formatar
        fmt: Formato (padrão: ISO 8601)
        tz: Timezone para converter antes de formatar
        
    Returns:
        String formatada
    """
    if tz is not None:
        dt = to_timezone(dt, tz)
    
    if fmt is None:
        return dt.isoformat()
    
    return dt.strftime(fmt)


def format_date(dt: _datetime | _date, fmt: str | None = None) -> str:
    """
    Formata data como string.
    
    Args:
        dt: Date ou datetime
        fmt: Formato (padrão: YYYY-MM-DD)
        
    Returns:
        String formatada
    """
    if isinstance(dt, _datetime):
        dt = dt.date()
    
    if fmt is None:
        fmt = _config._date_format
    
    return dt.strftime(fmt)


def format_time(dt: _datetime | _time, fmt: str | None = None) -> str:
    """
    Formata hora como string.
    
    Args:
        dt: Time ou datetime
        fmt: Formato (padrão: HH:MM:SS)
        
    Returns:
        String formatada
    """
    if isinstance(dt, _datetime):
        dt = dt.time()
    
    if fmt is None:
        fmt = _config._time_format
    
    return dt.strftime(fmt)


# =============================================================================
# Parsing
# =============================================================================

def parse_datetime(
    value: str,
    fmt: str | None = None,
    tz: _timezone | str | None = None,
) -> DateTime:
    """
    Parse string para DateTime.
    
    Args:
        value: String a parsear
        fmt: Formato (tenta ISO 8601 se None)
        tz: Timezone a aplicar se não presente na string
        
    Returns:
        DateTime
    """
    if fmt is None:
        # Tenta ISO 8601
        return DateTime.from_iso(value)
    
    dt = _datetime.strptime(value, fmt)
    
    if dt.tzinfo is None and tz is not None:
        if isinstance(tz, str):
            tz = get_timezone(tz)
        dt = dt.replace(tzinfo=tz)
    
    return DateTime.from_datetime(dt)


def parse_date(value: str, fmt: str | None = None) -> Date:
    """
    Parse string para Date.
    
    Args:
        value: String a parsear
        fmt: Formato (padrão: YYYY-MM-DD)
        
    Returns:
        Date
    """
    if fmt is None:
        fmt = _config._date_format
    
    return _datetime.strptime(value, fmt).date()


def parse_time(value: str, fmt: str | None = None) -> Time:
    """
    Parse string para Time.
    
    Args:
        value: String a parsear
        fmt: Formato (padrão: HH:MM:SS)
        
    Returns:
        Time
    """
    if fmt is None:
        fmt = _config._time_format
    
    return _datetime.strptime(value, fmt).time()


# =============================================================================
# Cálculos
# =============================================================================

def add_days(dt: _datetime, days: int) -> DateTime:
    """Adiciona dias a um datetime."""
    result = dt + timedelta(days=days)
    return DateTime.from_datetime(result)


def add_hours(dt: _datetime, hours: int) -> DateTime:
    """Adiciona horas a um datetime."""
    result = dt + timedelta(hours=hours)
    return DateTime.from_datetime(result)


def add_minutes(dt: _datetime, minutes: int) -> DateTime:
    """Adiciona minutos a um datetime."""
    result = dt + timedelta(minutes=minutes)
    return DateTime.from_datetime(result)


def add_seconds(dt: _datetime, seconds: int) -> DateTime:
    """Adiciona segundos a um datetime."""
    result = dt + timedelta(seconds=seconds)
    return DateTime.from_datetime(result)


def diff_seconds(dt1: _datetime, dt2: _datetime) -> float:
    """Retorna diferença em segundos entre dois datetimes."""
    return (dt1 - dt2).total_seconds()


def diff_minutes(dt1: _datetime, dt2: _datetime) -> float:
    """Retorna diferença em minutos entre dois datetimes."""
    return diff_seconds(dt1, dt2) / 60


def diff_hours(dt1: _datetime, dt2: _datetime) -> float:
    """Retorna diferença em horas entre dois datetimes."""
    return diff_seconds(dt1, dt2) / 3600


def diff_days(dt1: _datetime, dt2: _datetime) -> float:
    """Retorna diferença em dias entre dois datetimes."""
    return diff_seconds(dt1, dt2) / 86400


# =============================================================================
# Comparações
# =============================================================================

def normalize_for_comparison(dt: _datetime) -> _datetime:
    """
    Normaliza datetime para comparação segura.
    
    Se naive, assume UTC. Se aware, converte para UTC.
    Isso garante comparações consistentes entre datetimes
    naive e aware.
    
    Args:
        dt: Datetime a normalizar
        
    Returns:
        Datetime em UTC (aware)
    """
    if dt.tzinfo is None:
        # Naive - assume UTC
        return dt.replace(tzinfo=UTC)
    else:
        # Aware - converte para UTC
        return dt.astimezone(UTC)


def safe_compare(dt1: _datetime, dt2: _datetime) -> int:
    """
    Compara dois datetimes de forma segura, mesmo se um for naive e outro aware.
    
    Normaliza ambos para UTC antes de comparar.
    
    Args:
        dt1: Primeiro datetime
        dt2: Segundo datetime
        
    Returns:
        -1 se dt1 < dt2, 0 se iguais, 1 se dt1 > dt2
    """
    norm1 = normalize_for_comparison(dt1)
    norm2 = normalize_for_comparison(dt2)
    
    if norm1 < norm2:
        return -1
    elif norm1 > norm2:
        return 1
    return 0


def is_past(dt: _datetime) -> bool:
    """
    Verifica se datetime está no passado.
    
    Funciona com datetimes naive ou aware.
    """
    return safe_compare(dt, now()) < 0


def is_future(dt: _datetime) -> bool:
    """
    Verifica se datetime está no futuro.
    
    Funciona com datetimes naive ou aware.
    """
    return safe_compare(dt, now()) > 0


def is_today(dt: _datetime) -> bool:
    """Verifica se datetime é hoje."""
    dt_normalized = normalize_for_comparison(dt)
    return dt_normalized.date() == today(UTC)


def is_yesterday(dt: _datetime) -> bool:
    """Verifica se datetime é ontem."""
    dt_normalized = normalize_for_comparison(dt)
    return dt_normalized.date() == today(UTC) - timedelta(days=1)


def is_tomorrow(dt: _datetime) -> bool:
    """Verifica se datetime é amanhã."""
    dt_normalized = normalize_for_comparison(dt)
    return dt_normalized.date() == today(UTC) + timedelta(days=1)


# =============================================================================
# Ranges
# =============================================================================

def start_of_day(dt: _datetime) -> DateTime:
    """Retorna início do dia (00:00:00)."""
    return DateTime(dt.year, dt.month, dt.day, 0, 0, 0, 0, tzinfo=dt.tzinfo)


def end_of_day(dt: _datetime) -> DateTime:
    """Retorna fim do dia (23:59:59.999999)."""
    return DateTime(dt.year, dt.month, dt.day, 23, 59, 59, 999999, tzinfo=dt.tzinfo)


def start_of_month(dt: _datetime) -> DateTime:
    """Retorna início do mês."""
    return DateTime(dt.year, dt.month, 1, 0, 0, 0, 0, tzinfo=dt.tzinfo)


def end_of_month(dt: _datetime) -> DateTime:
    """Retorna fim do mês."""
    import calendar
    last_day = calendar.monthrange(dt.year, dt.month)[1]
    return DateTime(dt.year, dt.month, last_day, 23, 59, 59, 999999, tzinfo=dt.tzinfo)


def start_of_year(dt: _datetime) -> DateTime:
    """Retorna início do ano."""
    return DateTime(dt.year, 1, 1, 0, 0, 0, 0, tzinfo=dt.tzinfo)


def end_of_year(dt: _datetime) -> DateTime:
    """Retorna fim do ano."""
    return DateTime(dt.year, 12, 31, 23, 59, 59, 999999, tzinfo=dt.tzinfo)


# =============================================================================
# Classe timezone - API simplificada (estilo Django)
# =============================================================================

class timezone:
    """
    API simplificada para operações de data/hora.
    
    Todos os métodos retornam datetime em UTC por padrão.
    
    Uso:
        from core import timezone
        
        # Obter data/hora atual (UTC)
        now = timezone.now()
        today = timezone.today()
        
        # Converter para outro timezone
        local = timezone.localtime(now, "America/Sao_Paulo")
        
        # Verificações
        if timezone.is_past(some_date):
            ...
        
        # Formatação
        formatted = timezone.format(now, "%Y-%m-%d %H:%M")
        
        # Parsing
        dt = timezone.parse("2024-01-15T10:30:00Z")
    """
    
    # Constante UTC
    utc = UTC
    
    # =========================================================================
    # Obter data/hora
    # =========================================================================
    
    @staticmethod
    def now(tz: _timezone | str | None = None) -> DateTime:
        """
        Retorna datetime atual em UTC (ou timezone especificado).
        
        Args:
            tz: Timezone opcional (padrão: UTC)
            
        Returns:
            DateTime atual
            
        Exemplo:
            current = timezone.now()
            current_sp = timezone.now("America/Sao_Paulo")
        """
        return now(tz)
    
    @staticmethod
    def today(tz: _timezone | str | None = None) -> Date:
        """
        Retorna data atual.
        
        Args:
            tz: Timezone para determinar a data
            
        Returns:
            Data atual
        """
        return today(tz)
    
    @staticmethod
    def utcnow() -> DateTime:
        """Retorna datetime atual em UTC."""
        return utcnow()
    
    # =========================================================================
    # Conversão de timezone
    # =========================================================================
    
    @staticmethod
    def localtime(dt: _datetime, tz: _timezone | str | None = None) -> DateTime:
        """
        Converte datetime para timezone local/especificado.
        
        Args:
            dt: Datetime a converter
            tz: Timezone de destino
            
        Returns:
            DateTime convertido
            
        Exemplo:
            utc_time = timezone.now()
            local_time = timezone.localtime(utc_time, "America/Sao_Paulo")
        """
        if tz is None:
            tz = _config.default_timezone
        return to_timezone(dt, tz)
    
    @staticmethod
    def activate(tz: _timezone | str) -> None:
        """
        Define o timezone padrão.
        
        Args:
            tz: Timezone a usar como padrão
        """
        _config.default_timezone = tz if isinstance(tz, _timezone) else get_timezone(tz)
    
    @staticmethod
    def deactivate() -> None:
        """Reseta timezone para UTC."""
        _config.default_timezone = UTC
    
    @staticmethod
    def get_current_timezone() -> _timezone:
        """Retorna timezone atual configurado."""
        return _config.default_timezone
    
    @staticmethod
    def make_aware(dt: _datetime, tz: _timezone | str | None = None) -> DateTime:
        """
        Torna um datetime naive em aware.
        
        Args:
            dt: Datetime naive
            tz: Timezone a aplicar (padrão: UTC)
        """
        return make_aware(dt, tz)
    
    @staticmethod
    def make_naive(dt: _datetime, tz: _timezone | str | None = None) -> _datetime:
        """
        Remove timezone de um datetime.
        
        Args:
            dt: Datetime aware
            tz: Timezone para converter antes de remover
        """
        return make_naive(dt, tz)
    
    @staticmethod
    def is_aware(dt: _datetime) -> bool:
        """Verifica se datetime tem timezone."""
        return is_aware(dt)
    
    @staticmethod
    def is_naive(dt: _datetime) -> bool:
        """Verifica se datetime não tem timezone."""
        return is_naive(dt)
    
    @staticmethod
    def normalize(dt: _datetime) -> DateTime:
        """
        Normaliza datetime para UTC.
        
        Se naive, assume UTC. Se aware, converte para UTC.
        Útil para comparações seguras.
        
        Args:
            dt: Datetime a normalizar
            
        Returns:
            DateTime em UTC (aware)
        """
        return DateTime.from_datetime(normalize_for_comparison(dt))
    
    @staticmethod
    def safe_compare(dt1: _datetime, dt2: _datetime) -> int:
        """
        Compara dois datetimes de forma segura.
        
        Funciona mesmo se um for naive e outro aware.
        Normaliza ambos para UTC antes de comparar.
        
        Args:
            dt1: Primeiro datetime
            dt2: Segundo datetime
            
        Returns:
            -1 se dt1 < dt2, 0 se iguais, 1 se dt1 > dt2
        """
        return safe_compare(dt1, dt2)
    
    # =========================================================================
    # Verificações
    # =========================================================================
    
    @staticmethod
    def is_past(dt: _datetime) -> bool:
        """
        Verifica se datetime está no passado.
        
        Funciona com datetimes naive ou aware.
        """
        return is_past(dt)
    
    @staticmethod
    def is_future(dt: _datetime) -> bool:
        """
        Verifica se datetime está no futuro.
        
        Funciona com datetimes naive ou aware.
        """
        return is_future(dt)
    
    @staticmethod
    def is_today(dt: _datetime) -> bool:
        """Verifica se datetime é hoje."""
        return is_today(dt)
    
    @staticmethod
    def is_yesterday(dt: _datetime) -> bool:
        """Verifica se datetime é ontem."""
        return is_yesterday(dt)
    
    @staticmethod
    def is_tomorrow(dt: _datetime) -> bool:
        """Verifica se datetime é amanhã."""
        return is_tomorrow(dt)
    
    # =========================================================================
    # Formatação e Parsing
    # =========================================================================
    
    @staticmethod
    def format(
        dt: _datetime,
        fmt: str | None = None,
        tz: _timezone | str | None = None,
    ) -> str:
        """
        Formata datetime como string.
        
        Args:
            dt: Datetime a formatar
            fmt: Formato (padrão: ISO 8601)
            tz: Timezone para converter antes de formatar
        """
        return format_datetime(dt, fmt, tz)
    
    @staticmethod
    def parse(
        value: str,
        fmt: str | None = None,
        tz: _timezone | str | None = None,
    ) -> DateTime:
        """
        Parse string para DateTime.
        
        Args:
            value: String a parsear
            fmt: Formato (tenta ISO 8601 se None)
            tz: Timezone a aplicar se não presente
        """
        return parse_datetime(value, fmt, tz)
    
    # =========================================================================
    # Cálculos
    # =========================================================================
    
    @staticmethod
    def add(
        dt: _datetime,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
    ) -> DateTime:
        """
        Adiciona tempo a um datetime.
        
        Args:
            dt: Datetime base
            days: Dias a adicionar
            hours: Horas a adicionar
            minutes: Minutos a adicionar
            seconds: Segundos a adicionar
            
        Returns:
            Novo DateTime
            
        Exemplo:
            future = timezone.add(timezone.now(), days=7, hours=2)
        """
        result = dt + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        return DateTime.from_datetime(result)
    
    @staticmethod
    def subtract(
        dt: _datetime,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
    ) -> DateTime:
        """
        Subtrai tempo de um datetime.
        
        Args:
            dt: Datetime base
            days: Dias a subtrair
            hours: Horas a subtrair
            minutes: Minutos a subtrair
            seconds: Segundos a subtrair
        """
        result = dt - timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        return DateTime.from_datetime(result)
    
    @staticmethod
    def diff(dt1: _datetime, dt2: _datetime, unit: str = "seconds") -> float:
        """
        Calcula diferença entre dois datetimes.
        
        Args:
            dt1: Primeiro datetime
            dt2: Segundo datetime
            unit: Unidade ("seconds", "minutes", "hours", "days")
            
        Returns:
            Diferença na unidade especificada
        """
        seconds = diff_seconds(dt1, dt2)
        
        if unit == "minutes":
            return seconds / 60
        elif unit == "hours":
            return seconds / 3600
        elif unit == "days":
            return seconds / 86400
        
        return seconds
    
    # =========================================================================
    # Ranges
    # =========================================================================
    
    @staticmethod
    def start_of_day(dt: _datetime | None = None) -> DateTime:
        """Retorna início do dia (00:00:00)."""
        if dt is None:
            dt = now()
        return start_of_day(dt)
    
    @staticmethod
    def end_of_day(dt: _datetime | None = None) -> DateTime:
        """Retorna fim do dia (23:59:59.999999)."""
        if dt is None:
            dt = now()
        return end_of_day(dt)
    
    @staticmethod
    def start_of_month(dt: _datetime | None = None) -> DateTime:
        """Retorna início do mês."""
        if dt is None:
            dt = now()
        return start_of_month(dt)
    
    @staticmethod
    def end_of_month(dt: _datetime | None = None) -> DateTime:
        """Retorna fim do mês."""
        if dt is None:
            dt = now()
        return end_of_month(dt)
    
    @staticmethod
    def start_of_year(dt: _datetime | None = None) -> DateTime:
        """Retorna início do ano."""
        if dt is None:
            dt = now()
        return start_of_year(dt)
    
    @staticmethod
    def end_of_year(dt: _datetime | None = None) -> DateTime:
        """Retorna fim do ano."""
        if dt is None:
            dt = now()
        return end_of_year(dt)
    
    # =========================================================================
    # Criação
    # =========================================================================
    
    @staticmethod
    def datetime(
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
        tz: _timezone | str | None = None,
    ) -> DateTime:
        """
        Cria um DateTime.
        
        Args:
            year, month, day: Data
            hour, minute, second, microsecond: Hora
            tz: Timezone (padrão: UTC)
        """
        if tz is None:
            tz = UTC
        elif isinstance(tz, str):
            tz = get_timezone(tz)
        
        return DateTime(year, month, day, hour, minute, second, microsecond, tzinfo=tz)
    
    @staticmethod
    def from_timestamp(ts: float, tz: _timezone | str | None = None) -> DateTime:
        """Cria DateTime a partir de Unix timestamp."""
        return DateTime.from_timestamp(ts, tz)
    
    @staticmethod
    def from_iso(iso_string: str) -> DateTime:
        """Cria DateTime a partir de string ISO 8601."""
        return DateTime.from_iso(iso_string)
