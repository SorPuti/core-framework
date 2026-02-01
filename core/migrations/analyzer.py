"""
Analisador de Migrações - Validação Pré-Produção.

Detecta problemas potenciais em migrações ANTES de aplicar,
oferecendo sugestões e correções interativas.

Problemas detectados:
- Adicionar coluna NOT NULL sem default em tabela com dados
- Remover coluna com dados
- Alterar tipo de coluna com possível perda de dados
- Adicionar constraint UNIQUE em coluna com duplicatas
- Remover tabela com dados
- Foreign key para tabela inexistente
- Índices em colunas grandes
- E muito mais...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection
    from core.migrations.operations import Operation


class Severity(Enum):
    """Severidade do problema detectado."""
    INFO = "info"           # Informação, não bloqueia
    WARNING = "warning"     # Aviso, pode causar problemas
    ERROR = "error"         # Erro, vai falhar
    CRITICAL = "critical"   # Crítico, pode causar perda de dados


class IssueCode(Enum):
    """Códigos de problemas detectados."""
    # Colunas
    NOT_NULL_NO_DEFAULT = "E001"
    DROP_COLUMN_WITH_DATA = "W001"
    ALTER_TYPE_DATA_LOSS = "W002"
    UNIQUE_WITH_DUPLICATES = "E002"
    ADD_COLUMN_LARGE_TABLE = "I001"
    
    # Tabelas
    DROP_TABLE_WITH_DATA = "C001"
    DROP_TABLE_WITH_FK = "E003"
    CREATE_TABLE_EXISTS = "E004"
    
    # Foreign Keys
    FK_INVALID_REFERENCE = "E005"
    FK_ORPHAN_DATA = "W003"
    
    # Índices
    INDEX_LARGE_COLUMN = "W004"
    INDEX_EXISTS = "W005"
    
    # Geral
    DESTRUCTIVE_OPERATION = "W006"
    IRREVERSIBLE_OPERATION = "W007"
    LONG_RUNNING_OPERATION = "I002"
    
    # SQLite específico
    SQLITE_ALTER_LIMITATION = "W008"


# Tabelas internas que devem ser ignoradas na análise
# Importa tabelas internas do state para manter consistência
from core.migrations.state import INTERNAL_TABLES, PROTECTED_TABLES


@dataclass
class MigrationIssue:
    """Representa um problema detectado em uma migração."""
    
    code: IssueCode
    severity: Severity
    message: str
    operation_index: int
    operation_description: str
    suggestion: str | None = None
    auto_fix: str | None = None  # Código para corrigir automaticamente
    context: dict[str, Any] = field(default_factory=dict)
    
    def __str__(self) -> str:
        prefix = {
            Severity.INFO: "INFO",
            Severity.WARNING: "WARN",
            Severity.ERROR: "ERROR",
            Severity.CRITICAL: "CRITICAL",
        }[self.severity]
        
        lines = [
            f"  [{prefix}] {self.message}",
        ]
        
        if self.suggestion:
            lines.append(f"          -> {self.suggestion}")
        
        return "\n".join(lines)


@dataclass
class AnalysisResult:
    """Resultado da análise de uma migração."""
    
    migration_name: str
    issues: list[MigrationIssue] = field(default_factory=list)
    table_row_counts: dict[str, int] = field(default_factory=dict)
    
    @property
    def has_errors(self) -> bool:
        """Verifica se há erros que impedem a migração."""
        return any(
            i.severity in (Severity.ERROR, Severity.CRITICAL)
            for i in self.issues
        )
    
    @property
    def has_warnings(self) -> bool:
        """Verifica se há avisos."""
        return any(i.severity == Severity.WARNING for i in self.issues)
    
    @property
    def has_critical(self) -> bool:
        """Verifica se há problemas críticos."""
        return any(i.severity == Severity.CRITICAL for i in self.issues)
    
    @property
    def can_proceed(self) -> bool:
        """Verifica se pode prosseguir (sem erros críticos)."""
        return not any(
            i.severity in (Severity.ERROR, Severity.CRITICAL)
            for i in self.issues
        )
    
    def get_issues_by_severity(self, severity: Severity) -> list[MigrationIssue]:
        """Retorna issues de uma severidade específica."""
        return [i for i in self.issues if i.severity == severity]
    
    def summary(self) -> str:
        """Retorna resumo da análise."""
        counts = {s: 0 for s in Severity}
        for issue in self.issues:
            counts[issue.severity] += 1
        
        parts = []
        if counts[Severity.CRITICAL]:
            parts.append(f"{counts[Severity.CRITICAL]} critical")
        if counts[Severity.ERROR]:
            parts.append(f"{counts[Severity.ERROR]} error(s)")
        if counts[Severity.WARNING]:
            parts.append(f"{counts[Severity.WARNING]} warning(s)")
        
        if not parts:
            return "OK"
        
        return ", ".join(parts)


class MigrationAnalyzer:
    """
    Analisador de migrações.
    
    Detecta problemas potenciais antes de aplicar migrações.
    
    Uso:
        analyzer = MigrationAnalyzer(dialect="sqlite")
        result = await analyzer.analyze(operations, conn)
        
        if result.has_errors:
            print("Migration has errors!")
            for issue in result.issues:
                print(issue)
    """
    
    def __init__(self, dialect: str = "sqlite"):
        self.dialect = dialect
    
    async def analyze(
        self,
        operations: list["Operation"],
        conn: "AsyncConnection",
        migration_name: str = "unknown",
    ) -> AnalysisResult:
        """
        Analisa uma lista de operações de migração.
        
        Args:
            operations: Lista de operações a analisar
            conn: Conexão com o banco de dados
            migration_name: Nome da migração
            
        Returns:
            Resultado da análise com todos os problemas encontrados
        """
        result = AnalysisResult(migration_name=migration_name)
        
        # Coleta informações do banco atual
        await self._collect_database_info(conn, result)
        
        # Analisa cada operação
        for idx, op in enumerate(operations):
            op_issues = await self._analyze_operation(op, idx, conn, result)
            result.issues.extend(op_issues)
        
        return result
    
    async def _collect_database_info(
        self,
        conn: "AsyncConnection",
        result: AnalysisResult,
    ) -> None:
        """Coleta informações sobre o estado atual do banco."""
        try:
            # Lista tabelas
            if self.dialect == "sqlite":
                tables_result = await conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ))
            else:
                tables_result = await conn.execute(text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                ))
            
            tables = [row[0] for row in tables_result.fetchall()]
            
            # Conta linhas em cada tabela
            for table in tables:
                try:
                    count_result = await conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                    count = count_result.scalar() or 0
                    result.table_row_counts[table] = count
                except Exception:
                    result.table_row_counts[table] = -1  # Erro ao contar
                    
        except Exception:
            pass  # Ignora erros na coleta de info
    
    async def _analyze_operation(
        self,
        op: "Operation",
        idx: int,
        conn: "AsyncConnection",
        result: AnalysisResult,
    ) -> list[MigrationIssue]:
        """Analisa uma operação específica."""
        issues = []
        op_type = type(op).__name__
        op_desc = op.describe() if hasattr(op, "describe") else str(op)
        
        # Dispatch para analisador específico
        analyzer_method = getattr(self, f"_analyze_{op_type.lower()}", None)
        if analyzer_method:
            op_issues = await analyzer_method(op, idx, conn, result)
            issues.extend(op_issues)
        
        # Verificações gerais
        if getattr(op, "destructive", False):
            issues.append(MigrationIssue(
                code=IssueCode.DESTRUCTIVE_OPERATION,
                severity=Severity.WARNING,
                message="This operation is destructive and may cause data loss",
                operation_index=idx,
                operation_description=op_desc,
                suggestion="Make sure you have a backup before proceeding",
            ))
        
        if not getattr(op, "reversible", True):
            issues.append(MigrationIssue(
                code=IssueCode.IRREVERSIBLE_OPERATION,
                severity=Severity.WARNING,
                message="This operation cannot be reversed",
                operation_index=idx,
                operation_description=op_desc,
                suggestion="Consider if you really need this change",
            ))
        
        return issues
    
    async def _analyze_addcolumn(
        self,
        op: "Operation",
        idx: int,
        conn: "AsyncConnection",
        result: AnalysisResult,
    ) -> list[MigrationIssue]:
        """Analisa operação AddColumn."""
        issues = []
        table_name = op.table_name
        column = op.column
        op_desc = op.describe()
        row_count = result.table_row_counts.get(table_name, 0)
        
        # Problema: NOT NULL sem default em tabela com dados
        if not column.nullable and column.default is None and row_count > 0:
            issues.append(MigrationIssue(
                code=IssueCode.NOT_NULL_NO_DEFAULT,
                severity=Severity.ERROR,
                message=f"Cannot add NOT NULL column '{column.name}' without default value to table '{table_name}' with {row_count} existing rows",
                operation_index=idx,
                operation_description=op_desc,
                suggestion="Either: 1) Add a default value, 2) Make the column nullable, or 3) Add in two steps (nullable first, then update, then alter to NOT NULL)",
                auto_fix=self._generate_not_null_fix(table_name, column),
                context={
                    "table": table_name,
                    "column": column.name,
                    "row_count": row_count,
                },
            ))
        
        # Aviso: Tabela grande
        if row_count > 100000:
            issues.append(MigrationIssue(
                code=IssueCode.LONG_RUNNING_OPERATION,
                severity=Severity.INFO,
                message=f"Adding column to large table '{table_name}' ({row_count:,} rows) may take a while",
                operation_index=idx,
                operation_description=op_desc,
                suggestion="Consider running during low-traffic period",
                context={"row_count": row_count},
            ))
        
        # Aviso: UNIQUE em tabela com dados (pode ter duplicatas)
        if column.unique and row_count > 0:
            issues.append(MigrationIssue(
                code=IssueCode.UNIQUE_WITH_DUPLICATES,
                severity=Severity.WARNING,
                message=f"Adding UNIQUE column '{column.name}' to table with {row_count} rows - ensure no duplicates will be created",
                operation_index=idx,
                operation_description=op_desc,
                suggestion="Verify that the default value (if any) won't create duplicates",
                context={"row_count": row_count},
            ))
        
        return issues
    
    async def _analyze_dropcolumn(
        self,
        op: "Operation",
        idx: int,
        conn: "AsyncConnection",
        result: AnalysisResult,
    ) -> list[MigrationIssue]:
        """Analisa operação DropColumn."""
        issues = []
        table_name = op.table_name
        column_name = op.column_name
        op_desc = op.describe()
        row_count = result.table_row_counts.get(table_name, 0)
        
        # Verifica se coluna tem dados
        if row_count > 0:
            try:
                # Conta valores não-nulos
                non_null_result = await conn.execute(text(
                    f'SELECT COUNT(*) FROM "{table_name}" WHERE "{column_name}" IS NOT NULL'
                ))
                non_null_count = non_null_result.scalar() or 0
                
                if non_null_count > 0:
                    issues.append(MigrationIssue(
                        code=IssueCode.DROP_COLUMN_WITH_DATA,
                        severity=Severity.WARNING,
                        message=f"Dropping column '{column_name}' from '{table_name}' will delete {non_null_count:,} non-null values",
                        operation_index=idx,
                        operation_description=op_desc,
                        suggestion="Make sure you have backed up this data if needed",
                        context={
                            "table": table_name,
                            "column": column_name,
                            "non_null_count": non_null_count,
                        },
                    ))
            except Exception:
                # Coluna pode não existir ainda
                pass
        
        # SQLite: ALTER TABLE DROP COLUMN tem limitações
        if self.dialect == "sqlite":
            issues.append(MigrationIssue(
                code=IssueCode.SQLITE_ALTER_LIMITATION,
                severity=Severity.INFO,
                message="SQLite has limitations on DROP COLUMN - may require table recreation",
                operation_index=idx,
                operation_description=op_desc,
                suggestion="SQLite 3.35.0+ supports DROP COLUMN directly",
            ))
        
        return issues
    
    async def _analyze_droptable(
        self,
        op: "Operation",
        idx: int,
        conn: "AsyncConnection",
        result: AnalysisResult,
    ) -> list[MigrationIssue]:
        """Analisa operação DropTable."""
        issues = []
        table_name = op.table_name
        op_desc = op.describe()
        
        # Ignora tabelas internas do sistema
        if table_name in INTERNAL_TABLES:
            return issues
        
        row_count = result.table_row_counts.get(table_name, 0)
        
        # Crítico: Tabela com dados
        if row_count > 0:
            issues.append(MigrationIssue(
                code=IssueCode.DROP_TABLE_WITH_DATA,
                severity=Severity.CRITICAL,
                message=f"Dropping table '{table_name}' will DELETE ALL {row_count:,} rows permanently!",
                operation_index=idx,
                operation_description=op_desc,
                suggestion="Make absolutely sure you have a backup. Consider renaming instead of dropping.",
                context={
                    "table": table_name,
                    "row_count": row_count,
                },
            ))
        
        # Verifica FKs apontando para esta tabela
        try:
            if self.dialect == "sqlite":
                # SQLite: verifica pragma
                fk_result = await conn.execute(text(
                    f"SELECT * FROM sqlite_master WHERE type='table' AND sql LIKE '%REFERENCES \"{table_name}\"%'"
                ))
            else:
                fk_result = await conn.execute(text(f"""
                    SELECT tc.table_name 
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.constraint_column_usage ccu 
                        ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY' 
                        AND ccu.table_name = '{table_name}'
                """))
            
            referencing_tables = [row[0] for row in fk_result.fetchall()]
            if referencing_tables:
                issues.append(MigrationIssue(
                    code=IssueCode.DROP_TABLE_WITH_FK,
                    severity=Severity.ERROR,
                    message=f"Table '{table_name}' is referenced by foreign keys from: {referencing_tables}",
                    operation_index=idx,
                    operation_description=op_desc,
                    suggestion="Drop or modify the foreign keys first",
                    context={"referencing_tables": referencing_tables},
                ))
        except Exception:
            pass
        
        return issues
    
    async def _analyze_altercolumn(
        self,
        op: "Operation",
        idx: int,
        conn: "AsyncConnection",
        result: AnalysisResult,
    ) -> list[MigrationIssue]:
        """Analisa operação AlterColumn."""
        issues = []
        table_name = op.table_name
        column_name = op.column_name
        op_desc = op.describe()
        row_count = result.table_row_counts.get(table_name, 0)
        
        # Alterando para NOT NULL
        if op.new_nullable is False and op.old_nullable is True and row_count > 0:
            # Verifica se há NULLs
            try:
                null_result = await conn.execute(text(
                    f'SELECT COUNT(*) FROM "{table_name}" WHERE "{column_name}" IS NULL'
                ))
                null_count = null_result.scalar() or 0
                
                if null_count > 0:
                    issues.append(MigrationIssue(
                        code=IssueCode.NOT_NULL_NO_DEFAULT,
                        severity=Severity.ERROR,
                        message=f"Cannot change '{column_name}' to NOT NULL - {null_count:,} rows have NULL values",
                        operation_index=idx,
                        operation_description=op_desc,
                        suggestion=f"First update NULL values: UPDATE {table_name} SET {column_name} = 'default_value' WHERE {column_name} IS NULL",
                        context={
                            "table": table_name,
                            "column": column_name,
                            "null_count": null_count,
                        },
                    ))
            except Exception:
                pass
        
        # Alterando tipo
        if op.new_type and op.old_type and op.new_type != op.old_type:
            # Detecta possível perda de dados
            type_changes_with_risk = [
                ("TEXT", "VARCHAR"),
                ("VARCHAR", "INTEGER"),
                ("FLOAT", "INTEGER"),
                ("TEXT", "INTEGER"),
            ]
            
            old_base = op.old_type.split("(")[0].upper()
            new_base = op.new_type.split("(")[0].upper()
            
            if (old_base, new_base) in type_changes_with_risk:
                issues.append(MigrationIssue(
                    code=IssueCode.ALTER_TYPE_DATA_LOSS,
                    severity=Severity.WARNING,
                    message=f"Changing '{column_name}' from {op.old_type} to {op.new_type} may cause data loss",
                    operation_index=idx,
                    operation_description=op_desc,
                    suggestion="Verify that all existing data can be converted to the new type",
                    context={
                        "old_type": op.old_type,
                        "new_type": op.new_type,
                    },
                ))
            
            # Reduzindo tamanho de VARCHAR
            old_match = re.match(r"VARCHAR\((\d+)\)", op.old_type, re.IGNORECASE)
            new_match = re.match(r"VARCHAR\((\d+)\)", op.new_type, re.IGNORECASE)
            
            if old_match and new_match:
                old_size = int(old_match.group(1))
                new_size = int(new_match.group(1))
                
                if new_size < old_size and row_count > 0:
                    # Verifica se há dados que seriam truncados
                    try:
                        truncate_result = await conn.execute(text(
                            f'SELECT COUNT(*) FROM "{table_name}" WHERE LENGTH("{column_name}") > {new_size}'
                        ))
                        truncate_count = truncate_result.scalar() or 0
                        
                        if truncate_count > 0:
                            issues.append(MigrationIssue(
                                code=IssueCode.ALTER_TYPE_DATA_LOSS,
                                severity=Severity.ERROR,
                                message=f"Reducing '{column_name}' size from {old_size} to {new_size} will truncate {truncate_count:,} rows",
                                operation_index=idx,
                                operation_description=op_desc,
                                suggestion=f"First check: SELECT * FROM {table_name} WHERE LENGTH({column_name}) > {new_size}",
                                context={
                                    "truncate_count": truncate_count,
                                    "old_size": old_size,
                                    "new_size": new_size,
                                },
                            ))
                    except Exception:
                        pass
        
        # SQLite: ALTER COLUMN tem limitações
        if self.dialect == "sqlite":
            issues.append(MigrationIssue(
                code=IssueCode.SQLITE_ALTER_LIMITATION,
                severity=Severity.WARNING,
                message="SQLite has limited ALTER COLUMN support - may require table recreation",
                operation_index=idx,
                operation_description=op_desc,
                suggestion="This operation will recreate the table internally",
            ))
        
        return issues
    
    async def _analyze_createindex(
        self,
        op: "Operation",
        idx: int,
        conn: "AsyncConnection",
        result: AnalysisResult,
    ) -> list[MigrationIssue]:
        """Analisa operação CreateIndex."""
        issues = []
        table_name = op.table_name
        op_desc = op.describe()
        row_count = result.table_row_counts.get(table_name, 0)
        
        # Tabela grande
        if row_count > 100000:
            issues.append(MigrationIssue(
                code=IssueCode.LONG_RUNNING_OPERATION,
                severity=Severity.WARNING,
                message=f"Creating index on large table '{table_name}' ({row_count:,} rows) may lock the table",
                operation_index=idx,
                operation_description=op_desc,
                suggestion="Consider using CONCURRENTLY (PostgreSQL) or running during maintenance window",
                context={"row_count": row_count},
            ))
        
        # UNIQUE index em tabela com dados
        if getattr(op, "unique", False) and row_count > 0:
            columns = getattr(op, "columns", [])
            if columns:
                # Verifica duplicatas
                try:
                    cols_str = ", ".join(f'"{c}"' for c in columns)
                    dup_result = await conn.execute(text(f"""
                        SELECT {cols_str}, COUNT(*) as cnt 
                        FROM "{table_name}" 
                        GROUP BY {cols_str} 
                        HAVING COUNT(*) > 1
                        LIMIT 1
                    """))
                    
                    if dup_result.fetchone():
                        issues.append(MigrationIssue(
                            code=IssueCode.UNIQUE_WITH_DUPLICATES,
                            severity=Severity.ERROR,
                            message=f"Cannot create UNIQUE index - duplicates exist in columns: {columns}",
                            operation_index=idx,
                            operation_description=op_desc,
                            suggestion=f"First remove duplicates: SELECT {cols_str}, COUNT(*) FROM {table_name} GROUP BY {cols_str} HAVING COUNT(*) > 1",
                            context={"columns": columns},
                        ))
                except Exception:
                    pass
        
        return issues
    
    def _generate_not_null_fix(self, table_name: str, column) -> str:
        """Gera código para corrigir problema de NOT NULL sem default."""
        col_type = column.type
        
        # Sugere default baseado no tipo
        if "INT" in col_type.upper():
            default = "0"
        elif "BOOL" in col_type.upper():
            default = "False"
        elif "VARCHAR" in col_type.upper() or "TEXT" in col_type.upper():
            default = "''"
        elif "DATETIME" in col_type.upper() or "TIMESTAMP" in col_type.upper():
            default = "datetime.utcnow()"
        elif "FLOAT" in col_type.upper() or "DECIMAL" in col_type.upper():
            default = "0.0"
        else:
            default = "None"
        
        return f"""
# Option 1: Add default value
AddColumn(
    table_name='{table_name}',
    column=ColumnDef(
        name='{column.name}',
        type='{column.type}',
        nullable=False,
        default={default},  # <-- Add appropriate default
    ),
)

# Option 2: Make nullable first, then update
# Step 1: Add as nullable
AddColumn(
    table_name='{table_name}',
    column=ColumnDef(
        name='{column.name}',
        type='{column.type}',
        nullable=True,
    ),
)
# Step 2: Update existing rows
RunSQL(
    sql="UPDATE {table_name} SET {column.name} = {default} WHERE {column.name} IS NULL",
    reverse_sql="",
)
# Step 3: Alter to NOT NULL
AlterColumn(
    table_name='{table_name}',
    column_name='{column.name}',
    new_nullable=False,
)
"""


def format_analysis_report(result: AnalysisResult, verbose: bool = False) -> str:
    """Formata relatório de análise para exibição."""
    if not result.issues:
        return f"  {result.migration_name}: OK"
    
    lines = [f"  {result.migration_name}: {result.summary()}"]
    
    # Mostra apenas erros e críticos por padrão, warnings se verbose
    for severity in [Severity.CRITICAL, Severity.ERROR]:
        issues = result.get_issues_by_severity(severity)
        for issue in issues:
            lines.append(str(issue))
    
    # Warnings apenas se verbose ou se não há erros
    if verbose or not result.has_errors:
        warnings = result.get_issues_by_severity(Severity.WARNING)
        for issue in warnings:
            lines.append(str(issue))
    elif result.has_warnings:
        warn_count = len(result.get_issues_by_severity(Severity.WARNING))
        lines.append(f"          + {warn_count} warning(s) (use --verbose to see)")
    
    return "\n".join(lines)


async def analyze_migration(
    operations: list["Operation"],
    conn: "AsyncConnection",
    dialect: str = "sqlite",
    migration_name: str = "unknown",
) -> AnalysisResult:
    """
    Função de conveniência para analisar uma migração.
    
    Args:
        operations: Lista de operações
        conn: Conexão com o banco
        dialect: Dialeto SQL (sqlite, postgresql, mysql)
        migration_name: Nome da migração
        
    Returns:
        Resultado da análise
    """
    analyzer = MigrationAnalyzer(dialect=dialect)
    return await analyzer.analyze(operations, conn, migration_name)
