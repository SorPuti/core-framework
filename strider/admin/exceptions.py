"""
Exceções do Admin Panel.

Três níveis de erro, nenhum silencioso:

1. AdminConfigurationError -- Erro de setup, impede o boot.
2. AdminRegistrationError -- Erro de registro, model específico não sobe.
3. AdminRuntimeError -- Erro de banco/query em runtime, exibido na UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class AdminConfigurationError(Exception):
    """
    Erro fatal de configuração do admin.
    
    Impede o boot do admin panel. Stacktrace completo no terminal.
    
    Exemplos:
        - get_user_model() falhou (nenhum user model configurado)
        - Settings inválidos
        - Dependências faltando
    """
    pass


class AdminRegistrationError(Exception):
    """
    Erro de registro de model no admin.
    
    O model específico não sobe, mas demais modelos continuam funcionando.
    Validado no startup, não em runtime.
    
    Exemplos:
        - Campo inexistente em list_display
        - Tipo inválido em list_filter
        - Model não é subclasse de Model
    """
    
    def __init__(
        self,
        message: str,
        model_name: str | None = None,
        admin_class: str | None = None,
        source_file: str | None = None,
        available_fields: list[str] | None = None,
    ) -> None:
        self.model_name = model_name
        self.admin_class = admin_class
        self.source_file = source_file
        self.available_fields = available_fields
        
        detail_parts = [message]
        if available_fields:
            detail_parts.append(f"Available columns: {', '.join(available_fields)}")
        if source_file:
            detail_parts.append(f"Registered at: {source_file}")
        
        super().__init__("\n".join(detail_parts))


class AdminRuntimeError(Exception):
    """
    Erro de runtime do admin (banco, query, etc).
    
    Capturado e exibido na UI com hint de resolução.
    Nunca stacktrace cru no browser (exceto em debug=True).
    """
    
    def __init__(
        self,
        message: str,
        code: str = "unknown_error",
        hint: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.code = code
        self.hint = hint
        self.model_name = model_name
        super().__init__(message)


@dataclass
class AdminError:
    """
    Erro estruturado para exibição na UI do admin.
    
    Usado para coletar e exibir erros de forma profissional,
    com mensagens acionáveis e hints de resolução.
    """
    code: str               # "table_not_found", "connection_error", "import_error"
    title: str              # "Tabela não encontrada"
    detail: str             # "A tabela 'users' não existe no banco de dados."
    hint: str = ""          # "Execute 'core migrate' para criar as tabelas."
    model: str | None = None
    source: str | None = None   # Traceback resumido
    level: str = "error"        # "error", "warning", "info"


@dataclass
class AdminErrorCollector:
    """
    Coletor de erros do admin. Acumula erros durante boot/discovery
    para exibição consolidada no dashboard.
    
    Não engole erros — registra todos para exibição profissional.
    """
    errors: list[AdminError] = field(default_factory=list)
    
    def add(
        self,
        code: str,
        title: str,
        detail: str,
        hint: str = "",
        model: str | None = None,
        source: str | None = None,
        level: str = "error",
    ) -> None:
        """Registra um erro."""
        self.errors.append(AdminError(
            code=code,
            title=title,
            detail=detail,
            hint=hint,
            model=model,
            source=source,
            level=level,
        ))
    
    def add_discovery_error(
        self,
        module_path: str,
        error: Exception,
    ) -> None:
        """Registra erro de discovery (import falhou)."""
        import traceback
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        self.add(
            code="import_error",
            title=f"Falha ao importar {module_path}",
            detail=f"{type(error).__name__}: {error}",
            hint="Verifique imports e dependências no arquivo admin.py",
            source="".join(tb[-3:]),  # Últimas 3 linhas do traceback
            level="warning",
        )
    
    def add_registration_error(
        self,
        model_name: str,
        error: AdminRegistrationError,
    ) -> None:
        """Registra erro de registro de model."""
        self.add(
            code="registration_error",
            title=f"Erro ao registrar {model_name}",
            detail=str(error),
            hint="Verifique a configuração do ModelAdmin",
            model=model_name,
            source=error.source_file,
            level="error",
        )
    
    def add_runtime_error(
        self,
        model_name: str,
        error: Exception,
        hint: str = "",
    ) -> None:
        """Registra erro de runtime (banco, query, etc)."""
        import traceback
        
        # Detectar tipo de erro para hint automático
        error_str = str(error).lower()
        if not hint:
            if "no such table" in error_str or "relation" in error_str and "does not exist" in error_str:
                hint = "Execute 'core migrate' para criar as tabelas."
            elif "connection" in error_str:
                hint = "Verifique se o banco de dados está acessível."
            else:
                hint = "Verifique os logs para mais detalhes."
        
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        self.add(
            code="runtime_error",
            title=f"Erro em {model_name}",
            detail=f"{type(error).__name__}: {error}",
            hint=hint,
            model=model_name,
            source="".join(tb[-3:]),
            level="error",
        )
    
    @property
    def has_errors(self) -> bool:
        return any(e.level == "error" for e in self.errors)
    
    @property
    def has_warnings(self) -> bool:
        return any(e.level == "warning" for e in self.errors)
    
    @property
    def error_count(self) -> int:
        return sum(1 for e in self.errors if e.level == "error")
    
    @property
    def warning_count(self) -> int:
        return sum(1 for e in self.errors if e.level == "warning")
    
    def get_errors_for_model(self, model_name: str) -> list[AdminError]:
        """Retorna erros de um model específico."""
        return [e for e in self.errors if e.model == model_name]
    
    def to_dict(self) -> list[dict]:
        """Serializa para JSON (usado pela API e templates)."""
        return [
            {
                "code": e.code,
                "title": e.title,
                "detail": e.detail,
                "hint": e.hint,
                "model": e.model,
                "source": e.source,
                "level": e.level,
            }
            for e in self.errors
        ]
