"""
Classe base para migrações.

Cada arquivo de migração contém uma classe Migration que herda desta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.migrations.operations import Operation


@dataclass
class Migration:
    """
    Representa uma migração.
    
    Exemplo de arquivo de migração (migrations/0001_initial.py):
    
        from core.migrations import Migration, CreateTable, ColumnDef
        
        class Migration(Migration):
            dependencies = []
            
            operations = [
                CreateTable(
                    table_name='users',
                    columns=[
                        ColumnDef(name='id', type='INTEGER', primary_key=True, autoincrement=True),
                        ColumnDef(name='email', type='VARCHAR(255)', nullable=False, unique=True),
                        ColumnDef(name='name', type='VARCHAR(100)', nullable=False),
                        ColumnDef(name='is_active', type='BOOLEAN', default=True),
                    ],
                ),
            ]
    """
    
    # Nome único da migração (ex: "0001_initial")
    name: str = ""
    
    # App/módulo a que pertence
    app_label: str = ""
    
    # Migrações das quais esta depende
    # Formato: [("app_label", "migration_name"), ...]
    dependencies: list[tuple[str, str]] = field(default_factory=list)
    
    # Lista de operações a executar
    operations: list["Operation"] = field(default_factory=list)
    
    # Se True, esta é uma migração inicial (cria tabelas do zero)
    initial: bool = False
    
    def __post_init__(self):
        # Extrai nome do arquivo se não fornecido
        if not self.name and hasattr(self, "__module__"):
            # Ex: "migrations.0001_initial" -> "0001_initial"
            self.name = self.__module__.split(".")[-1]
    
    @property
    def is_reversible(self) -> bool:
        """Verifica se todas as operações são reversíveis."""
        return all(op.reversible for op in self.operations)
    
    @property
    def has_destructive_operations(self) -> bool:
        """Verifica se há operações destrutivas."""
        return any(op.destructive for op in self.operations)
    
    def describe(self) -> str:
        """Descrição legível da migração."""
        lines = [f"Migration: {self.name}"]
        if self.dependencies:
            deps = ", ".join(f"{app}.{name}" for app, name in self.dependencies)
            lines.append(f"  Dependencies: {deps}")
        lines.append("  Operations:")
        for op in self.operations:
            lines.append(f"    - {op.describe()}")
        return "\n".join(lines)
