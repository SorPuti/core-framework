"""
Helpers de relacionamento para modelos SQLAlchemy (``Rel``, ``AssociationTable``).

Dois formatos de string distintos
================================

1. **Coluna FK (SQL):** ``Rel.foreign_key("tabela.coluna")``

   - Formato: ``nome_da_tabela.nome_da_coluna`` (ex.: ``users.id``, ``public.users.id`` —
     usa-se o par ``(tabela, coluna)`` extraído do final da string).
   - Deve coincidir com ``__tablename__`` e o nome da coluna referenciada no banco.
   - **Inferência de tipo:** se ``type_`` for omitido, o tipo SQLAlchemy da FK
     (``Integer``, UUID PostgreSQL, ``BigInteger``) é inferido procurando uma
     subclasse de ``Model`` com esse ``__tablename__`` e inspecionando a PK ou a
     coluna. O modelo referenciado deve **já estar definido** como classe (tipicamente
     declarado **antes** no mesmo módulo ou importado antes). Se não for encontrado,
     assume-se **inteiro** (``int``).

2. **Alvo de ``relationship()`` (app Django-style):** ``"app_label.ModelName"``

   - Padrão obrigatório para ``Rel.many_to_one``, ``one_to_many``, ``one_to_one``,
     ``many_to_many`` quando o target é resolvido via ``_resolve_target_to_class``.
   - Regex: ``RELATIONSHIP_TARGET_PATTERN`` — exatamente **um** ponto, identificadores
     ``[a-zA-Z_][a-zA-Z0-9_]*`` em ambos os lados (ex.: ``core.User``, ``strategies.Strategy``).
   - Resolução: import dinâmico de ``src.apps.<app_label>.models`` e obtenção do
     atributo ``ModelName``. Falhas levantam ``ValueError`` (formato), ``ImportError``
     (módulo inexistente) ou ``AttributeError`` (classe ausente no módulo).

3. **Validação rígida com encerramento do processo**

   Ao usar ``foreign_keys=[...]`` como **nomes de atributos** em ``many_to_one`` /
   ``one_to_many`` / ``one_to_one``, o framework usa um descriptor que, em
   ``__set_name__``, chama ``_validate_relationship_target``. Se o ``target`` **não**
   seguir ``app_label.ModelName``, uma mensagem é impressa em stderr e o processo
   termina com ``sys.exit(0)`` (comportamento intencional para falha visível em dev).

Exemplo mínimo::

    from strider import Model, Field
    from strider.relations import Rel

    class Author(Model):
        __tablename__ = "authors"
        id: Mapped[int] = Field.pk()
        name: Mapped[str] = Field.string(max_length=100)
        posts: Mapped[list["Post"]] = Rel.one_to_many(
            "core.Post",
            back_populates="author",
        )

    class Post(Model):
        __tablename__ = "posts"
        id: Mapped[int] = Field.pk()
        title: Mapped[str] = Field.string(max_length=200)
        author_id: Mapped[int] = Rel.foreign_key("authors.id")
        author: Mapped["Author"] = Rel.many_to_one(
            "core.Author",
            back_populates="posts",
        )
"""

from __future__ import annotations

import logging
import re
import sys
from typing import TYPE_CHECKING, Any, TypeVar, overload
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from strider.models import Model

T = TypeVar("T", bound="Model")

logger = logging.getLogger("strider.relations")


def _parse_fk_target(target: str) -> tuple[str, str] | None:
    """Extrai (tabela, coluna) de ``table.column`` ou ``schema.table.column``."""
    parts = target.split(".")
    if len(parts) < 2:
        return None
    return parts[-2], parts[-1]


def _find_model_class_by_tablename(table_name: str) -> type | None:
    """
    Encontra uma classe Model cuja ``__tablename__`` coincide com ``table_name``.

    Percorre a árvore de subclasses de ``Model``; em último caso tenta o registry
    do SQLAlchemy (útil quando o mapper já foi configurado).
    """
    from strider.models import Model

    found: list[type] = []
    seen: set[int] = set()

    def walk(base: type) -> None:
        for sub in base.__subclasses__():
            sid = id(sub)
            if sid in seen:
                continue
            seen.add(sid)
            if getattr(sub, "__abstract__", False):
                walk(sub)
                continue
            if getattr(sub, "__tablename__", None) == table_name:
                found.append(sub)
            walk(sub)

    walk(Model)
    if found:
        return found[0]

    try:
        for mapper in Model.registry.mappers:
            cls = mapper.class_
            if getattr(cls, "__tablename__", None) == table_name:
                return cls
    except Exception:
        pass
    return None


def _infer_fk_type_kind(target: str) -> str:
    """
    Deduz ``uuid`` / ``bigint`` / ``int`` a partir do modelo e coluna referenciados.

    Usa a mesma detecção de PK que ``_get_pk_column_type`` (auth) para ``.id``;
    para outras colunas, inspeciona ``__table__`` ou anotações quando possível.
    Se não houver modelo ou não for possível inferir, retorna ``int``.
    """
    from sqlalchemy import BigInteger, Integer
    from sqlalchemy import Uuid as SAUuid
    from sqlalchemy.dialects.postgresql import UUID as PgUUID

    parsed = _parse_fk_target(target)
    if not parsed:
        return "int"

    table_name, column_name = parsed
    model_class = _find_model_class_by_tablename(table_name)
    if model_class is None:
        return "int"

    from strider.auth.models import _get_pk_column_type

    if column_name == "id":
        dt = _get_pk_column_type(model_class)
        if dt == PgUUID:
            return "uuid"
        if dt == BigInteger:
            return "bigint"
        return "int"

    if hasattr(model_class, "__table__") and model_class.__table__ is not None:
        try:
            col = model_class.__table__.columns.get(column_name)
            if col is not None:
                ct = col.type
                if isinstance(ct, (PgUUID, SAUuid)) or "UUID" in type(ct).__name__.upper():
                    return "uuid"
                if isinstance(ct, BigInteger):
                    return "bigint"
                if isinstance(ct, Integer):
                    return "int"
        except Exception:
            pass

    for base in model_class.__mro__:
        annotations = getattr(base, "__annotations__", {})
        if column_name not in annotations:
            continue
        ann_s = str(annotations[column_name])
        if "UUID" in ann_s or "Uuid" in ann_s or "uuid" in ann_s:
            return "uuid"

    return "int"


# Alvo de relationship: exatamente "app_label.ModelName" (um ponto, dois identificadores).
# Resolução: importlib.import_module("src.apps.<app_label>.models") → getattr(ModelName).
RELATIONSHIP_TARGET_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*$")


# =============================================================================
# Association Table Builder
# =============================================================================

class AssociationTable:
    """
    Construtor de tabelas de junção (N para N) no ``metadata`` do ``Model``.

    **Formato dos lados**

    - ``left`` / ``right``: tupla ``(nome_coluna_local, alvo_fk_sql)``, onde
      ``alvo_fk_sql`` segue o mesmo formato que ``Rel.foreign_key``:
      ``"tabela.coluna"`` (ex.: ``"posts.id"``).

    **Limitação atual**

    As duas FKs da tabela gerada usam tipo **Integer** internamente. Para PKs UUID
    ou ``bigint``, crie a ``Table`` manualmente com os tipos corretos ou estenda
    este helper no futuro.

    **Cache**

    Tabelas criadas ficam em cache por nome; ``get(name)`` retorna a instância
    existente; ``clear_cache()`` esvazia (útil em testes).

    Exemplo::

        post_tags = AssociationTable.create(
            "post_tags",
            left=("post_id", "posts.id"),
            right=("tag_id", "tags.id"),
        )
    """
    
    _tables: dict[str, Table] = {}
    
    @classmethod
    def create(
        cls,
        name: str,
        left: tuple[str, str],
        right: tuple[str, str],
        *,
        metadata: Any = None,
        extra_columns: list[Column] | None = None,
        ondelete: str = "CASCADE",
    ) -> Table:
        """
        Cria (ou reutiliza do cache) uma ``Table`` de associação com duas FKs inteiras.

        Parâmetros
        ----------
        name:
            Nome da tabela SQL.
        left, right:
            ``(nome_coluna, "tabela_referenciada.coluna")`` para cada lado.
        metadata:
            ``MetaData`` SQLAlchemy; o padrão é ``Model.metadata``.
        extra_columns:
            Colunas extras (ex.: timestamp de vínculo).
        ondelete:
            Ação ``ON DELETE`` nas FKs (padrão ``CASCADE``).

        Retorno
        -------
        Instância ``sqlalchemy.Table`` registrada no metadata.
        """
        if name in cls._tables:
            return cls._tables[name]
        
        if metadata is None:
            from strider.models import Model
            metadata = Model.metadata
        
        left_col, left_fk = left
        right_col, right_fk = right
        
        columns = [
            Column(
                left_col,
                Integer,
                ForeignKey(left_fk, ondelete=ondelete),
                primary_key=True,
            ),
            Column(
                right_col,
                Integer,
                ForeignKey(right_fk, ondelete=ondelete),
                primary_key=True,
            ),
        ]
        
        if extra_columns:
            columns.extend(extra_columns)
        
        table = Table(
            name,
            metadata,
            *columns,
            extend_existing=True,
        )
        
        cls._tables[name] = table
        return table
    
    @classmethod
    def get(cls, name: str) -> Table | None:
        """Retorna a ``Table`` em cache pelo nome, ou ``None``."""
        return cls._tables.get(name)
    
    @classmethod
    def clear_cache(cls) -> None:
        """Remove todas as tabelas do cache interno (útil em testes)."""
        cls._tables.clear()


# =============================================================================
# Relationship Helpers
# =============================================================================

def _app_label_from_module(module_name: str) -> str | None:
    """
    Extrai o app_label do módulo do modelo.
    Ex: "src.apps.core.models" -> "core"
    """
    if not module_name or "src.apps." not in module_name:
        return None
    parts = module_name.split(".")
    try:
        idx = parts.index("apps")
        if idx + 2 < len(parts):
            return parts[idx + 2]
    except ValueError:
        pass
    return None


def _validate_relationship_target(target: str, owner: type, attr_name: str) -> None:
    """
    Valida que o target segue o padrão app_label.ModelName.
    Se não seguir, imprime mensagem explicativa e encerra com sys.exit(0).
    """
    if RELATIONSHIP_TARGET_PATTERN.match(target):
        return
    app_label = _app_label_from_module(owner.__module__)
    suggestion = f"{app_label}.{target}" if app_label else f"<app_label>.{target}"
    msg = (
        f"\n{'='*60}\n"
        "Relacionamento fora do padrão obrigatório.\n"
        f"{'='*60}\n\n"
        f"  Modelo:  {owner.__module__}.{owner.__name__}\n"
        f"  Atributo: {attr_name}\n"
        f"  Valor atual: {target!r}\n\n"
        "O framework exige o padrão Django: app_label.ModelName\n"
        "  - app_label = pasta do app em src.apps (ex: core, strategies)\n"
        "  - ModelName = nome da classe do model em src.apps.<app_label>.models\n\n"
        f"Substitua por: {suggestion!r}\n\n"
        "Exemplo: Rel.many_to_one(\"core.User\", ...) em vez de Rel.many_to_one(\"User\", ...)\n"
        f"{'='*60}\n"
    )
    print(msg, file=sys.stderr)
    sys.exit(0)


def _get_registry_from_class(cls: type) -> Any:
    """Obtém o registry do SQLAlchemy a partir de uma classe mapeada."""
    for c in cls.__mro__:
        if hasattr(c, "registry"):
            return c.registry
    return None


def _get_target_class(owner_class: type, target: str) -> type | None:
    """Resolve o nome do modelo (string) para a classe, via registry da base."""
    registry = _get_registry_from_class(owner_class)
    if registry is None:
        return None
    reg = getattr(registry, "_class_registry", None)
    if reg is None:
        return None
    val = reg.get(target)
    if val is None:
        return None
    # Pode ser _MultipleClassMarker com .contents (weakref.ref para classes)
    if hasattr(val, "contents"):
        refs = getattr(val, "contents", ())
        if refs:
            first_ref = next(iter(refs))
            return first_ref() if callable(first_ref) else first_ref
        return None
    return val


def _resolve_foreign_keys_to_columns(
    owner_class: type,
    target: str | type,
    foreign_keys: list[str],
    side: str,
) -> list[Any]:
    """
    Converte nomes de coluna (strings) em Column objects para relationship().
    SQLAlchemy 2.0 exige Column objects em foreign_keys, não strings.
    target pode ser o nome da classe (str) ou a classe (type) para one_to_many.
    """
    if side == "many_to_one":
        return [getattr(owner_class, name) for name in foreign_keys]
    if isinstance(target, type):
        target_class = target
    else:
        target_class = _get_target_class(owner_class, target)
    if target_class is None:
        raise ValueError(
            f"Não foi possível resolver a classe alvo {target!r} para "
            "foreign_keys. Use o padrão app_label.ModelName (ex: core.User)."
        )
    return [getattr(target_class, name) for name in foreign_keys]


class _RelationshipDescriptor:
    """
    Descriptor que atrasa a criação do relationship() até __set_name__,
    quando a classe já existe e podemos resolver foreign_keys (strings -> Columns).
    Necessário porque SQLAlchemy 2.0 exige Column objects em foreign_keys.
    """

    def __init__(
        self,
        target: str,
        side: str,
        kwargs: dict[str, Any],
        foreign_keys_names: list[str],
    ):
        self._target = target
        self._side = side
        self._kwargs = kwargs
        self._foreign_keys_names = foreign_keys_names

    def __set_name__(self, owner: type, name: str) -> None:
        _validate_relationship_target(self._target, owner, name)
        try:
            resolved_class = _resolve_target_to_class(self._target)
            fk_columns = _resolve_foreign_keys_to_columns(
                owner, resolved_class, self._foreign_keys_names, self._side
            )
            kwargs = {**self._kwargs, "foreign_keys": fk_columns}
            rel = relationship(resolved_class, **kwargs)
        except AttributeError:
            # Import circular: o model alvo ainda não foi definido no módulo.
            # Passamos string para o SQLAlchemy resolver depois e foreign_keys como callable.
            target_str = self._target
            fk_names = self._foreign_keys_names
            side = self._side

            def _lazy_foreign_keys() -> list[Any]:
                cls = _resolve_target_to_class(target_str)
                return _resolve_foreign_keys_to_columns(owner, cls, fk_names, side)

            lazy_target = _target_to_lazy_string(self._target)
            kwargs = {**self._kwargs, "foreign_keys": _lazy_foreign_keys}
            rel = relationship(lazy_target, **kwargs)
        setattr(owner, name, rel)


class _SelfReferentialDescriptor:
    """
    Descriptor para self_referential que resolve foreign_keys e remote_side
    (strings) para Column objects em __set_name__.
    """

    def __init__(
        self,
        *,
        back_populates: str | None,
        lazy: str,
        cascade: str,
        uselist: bool,
        foreign_keys: str | None,
        remote_side: str | None,
    ):
        self._back_populates = back_populates
        self._lazy = lazy
        self._cascade = cascade
        self._uselist = uselist
        self._foreign_keys = foreign_keys
        self._remote_side = remote_side

    def __set_name__(self, owner: type, name: str) -> None:
        kwargs: dict[str, Any] = {
            "back_populates": self._back_populates,
            "lazy": self._lazy,
            "cascade": self._cascade,
            "uselist": self._uselist,
        }
        if self._foreign_keys:
            kwargs["foreign_keys"] = [getattr(owner, self._foreign_keys)]
        if self._remote_side:
            kwargs["remote_side"] = [getattr(owner, self._remote_side)]
        argument = "self" if self._back_populates else None
        setattr(owner, name, relationship(argument, **kwargs))


def _resolve_target(target: str) -> str:
    """
    Compatibilidade: ``_resolve_target_to_class(target).__name__``.

    Preferir ``_resolve_target_to_class`` para obter a classe.
    """
    cls = _resolve_target_to_class(target)
    return cls.__name__


def _resolve_target_to_class(target: str) -> type:
    """
    Resolve ``"app_label.ModelName"`` para a classe Python do modelo.

    - Valida o formato com ``RELATIONSHIP_TARGET_PATTERN``; caso contrário,
      ``ValueError``.
    - Importa ``src.apps.<app_label>.models`` e faz ``getattr(module, ModelName)``.
    - ``ImportError`` se o módulo não existir; ``AttributeError`` se a classe não
      estiver definida no módulo.
    """
    if not RELATIONSHIP_TARGET_PATTERN.match(target):
        raise ValueError(
            "Target de relacionamento deve ser app_label.ModelName "
            "(ex: core.User, strategies.Strategy). "
            "O model deve estar em src.apps.<app_label>.models"
        )
    from importlib import import_module
    app_label, model_name = target.split(".", 1)
    module_path = f"src.apps.{app_label}.models"
    try:
        module = import_module(module_path)
    except ImportError as e:
        raise ImportError(
            f"Não foi possível importar {module_path!r} para o target {target!r}. "
            "Verifique que o app existe em src.apps e que o model está em models.py."
        ) from e
    if not hasattr(module, model_name):
        raise AttributeError(
            f"Model {model_name!r} não encontrado em {module_path}. "
            f"Classes disponíveis: {[x for x in dir(module) if not x.startswith('_')]}"
        )
    return getattr(module, model_name)


def _target_to_lazy_string(target: str) -> str:
    """
    Se ``target`` for ``app_label.ModelName``, devolve
    ``"src.apps.<app_label>.models.<ModelName>"`` para o SQLAlchemy resolver mais tarde;
    caso contrário devolve ``target`` inalterado.
    """
    if not RELATIONSHIP_TARGET_PATTERN.match(target):
        return target
    app_label, model_name = target.split(".", 1)
    return f"src.apps.{app_label}.models.{model_name}"


# Cache de módulos já tentados (evita importações repetidas)
_model_import_cache: dict[str, bool] = {}


def clear_model_cache() -> None:
    """
    Limpa ``_model_import_cache`` (cache interno reservado para importação de models).

    Hoje pouco populado pelo restante do módulo; mantido para testes e evolução futura.
    """
    global _model_import_cache
    _model_import_cache.clear()
    logger.debug("Model import cache cleared")


class Rel:
    """
    API estática estilo Django para colunas FK e ``relationship()`` do SQLAlchemy.

    **Resumo**

    ========================  ======================================
    Método                    Papel
    ========================  ======================================
    ``foreign_key``           Coluna mapeada + ``ForeignKey`` (string SQL)
    ``many_to_one``           N:1 no lado "muitos" (``belongs_to``)
    ``one_to_many``           1:N no lado "um" (``has_many``)
    ``one_to_one``            1:1
    ``many_to_many``          N:N via tabela ``secondary``
    ``self_referential``      Mesma tabela (árvore, etc.)
    ========================  ======================================

    **Targets**

    - ``foreign_key``: apenas ``"tabela.coluna"`` (ver docstring do método).
    - Demais métodos: ``target`` deve ser ``"app_label.ModelName"`` salvo uso avançado
      com ``foreign_keys`` como lista de nomes de atributos (ver cada método).

    **Aliases:** ``belongs_to`` = ``many_to_one``; ``has_many`` = ``one_to_many``;
    ``has_one`` = ``one_to_one``.
    """
    
    # -------------------------------------------------------------------------
    # Foreign Key
    # -------------------------------------------------------------------------
    
    @staticmethod
    def foreign_key(
        target: str,
        *,
        nullable: bool = False,
        ondelete: str = "CASCADE",
        index: bool = True,
        type_: str | None = None,
    ) -> Mapped[int] | Mapped[int | None] | Mapped[UUID] | Mapped[UUID | None]:
        """
        Declara uma coluna com ``ForeignKey`` para ``target``.

        **Formato de ``target``**

        - Obrigatório: ``"<tabela>.<coluna>"`` com pelo menos um ponto. Aceita esquema
          no prefixo (ex.: ``"public.users.id"``): a tabela e a coluna usadas são os
          **dois últimos** segmentos (``users``, ``id``).
        - Deve coincidir com o nome físico da tabela/coluna referenciada.

        **Parâmetros**

        - ``nullable``: se ``True``, a coluna permite ``NULL`` (use ``Mapped[T | None]``).
        - ``ondelete``: repasse ao PostgreSQL/SQLAlchemy (``CASCADE``, ``SET NULL``,
          ``RESTRICT``, ``NO ACTION``, …). Com ``SET NULL`` costuma-se ``nullable=True``.
        - ``index``: cria índice na coluna da FK (recomendado ``True``).
        - ``type_``:
            - ``None`` (padrão): infere ``int``, ``uuid`` ou ``bigint`` conforme o
              modelo referenciado (via ``__tablename__``) e a coluna; ver módulo.
            - ``"int"`` | ``"uuid"`` | ``"bigint"``: força o tipo (sobrescreve a inferência).

        **Validação / limitações**

        - Não há regex além de poder partir ``target`` em tabela/coluna; nomes inválidos
          falham na criação do schema ou em runtime no banco.
        - Se o modelo alvo não for encontrado na árvore de ``Model``, a inferência cai
          em **inteiro**.

        **Retorno**

        ``MappedColumn`` compatível com anotações ``Mapped[int]``, ``Mapped[UUID]``, etc.
        """
        from sqlalchemy import BigInteger
        from sqlalchemy.dialects.postgresql import UUID as PgUUID

        effective = type_ if type_ is not None else _infer_fk_type_kind(target)
        
        if effective == "uuid":
            return mapped_column(
                PgUUID(as_uuid=True),
                ForeignKey(target, ondelete=ondelete),
                nullable=nullable,
                index=index,
            )
        elif effective == "bigint":
            return mapped_column(
                BigInteger,
                ForeignKey(target, ondelete=ondelete),
                nullable=nullable,
                index=index,
            )
        else:
            return mapped_column(
                Integer,
                ForeignKey(target, ondelete=ondelete),
                nullable=nullable,
                index=index,
            )
    
    # -------------------------------------------------------------------------
    # Many-to-One (belongs_to)
    # -------------------------------------------------------------------------
    
    @staticmethod
    def many_to_one(
        target: str,
        *,
        back_populates: str | None = None,
        backref: str | None = None,
        lazy: str = "selectin",
        foreign_keys: list[str] | None = None,
        uselist: bool = False,
    ) -> Mapped[Any]:
        """
        Relacionamento **muitos-para-um** (lado "N" aponta para um registo do alvo).

        **Formato de ``target``**

        - Caminho normal: ``"app_label.ModelName"`` (ex.: ``"core.Author"``). Tem de
          casar com ``RELATIONSHIP_TARGET_PATTERN``. O modelo é carregado de
          ``src.apps.<app_label>.models``.
        - Se ``foreign_keys`` for uma **lista de strings** (nomes de atributos na
          classe actual que são colunas FK), usa-se um descriptor interno: aí
          ``target`` também deve ser ``app_label.ModelName`` e, se inválido,
          ``_validate_relationship_target`` pode terminar o processo com ``sys.exit(0)``.

        **Parâmetros**

        - ``back_populates``: nome do atributo ``relationship`` no modelo **alvo**.
        - ``backref``: atalho SQLAlchemy para criar o lado inverso (alternativa a
          ``back_populates``).
        - ``lazy``: ``"selectin"`` (padrão), ``"joined"``, ``"subquery"``, ``"select"``, etc.
        - ``foreign_keys``: lista de colunas FK quando há ambiguidade; ver strings acima.
        - ``uselist``: para muitos-para-um deve ser ``False`` (padrão).

        **Erros comuns**

        - ``ValueError``: ``target`` não está no formato ``app_label.ModelName``.
        - ``ImportError`` / ``AttributeError``: módulo ou classe do modelo inexistente.

        **Alias:** ``Rel.belongs_to``.
        """
        if foreign_keys and isinstance(foreign_keys, list) and all(
            isinstance(x, str) for x in foreign_keys
        ):
            return _RelationshipDescriptor(
                target,
                "many_to_one",
                dict(
                    back_populates=back_populates,
                    backref=backref,
                    lazy=lazy,
                    uselist=False,
                ),
                foreign_keys,
            )
        resolved = _resolve_target_to_class(target)
        return relationship(
            resolved,
            back_populates=back_populates,
            backref=backref,
            lazy=lazy,
            foreign_keys=foreign_keys,
            uselist=False,  # Many-to-one always returns single object
        )
    
    # Alias for Django users
    belongs_to = many_to_one
    
    # -------------------------------------------------------------------------
    # One-to-Many (has_many)
    # -------------------------------------------------------------------------
    
    @staticmethod
    def one_to_many(
        target: str,
        *,
        back_populates: str | None = None,
        backref: str | None = None,
        lazy: str = "selectin",
        foreign_keys: list[str] | None = None,
        cascade: str = "all, delete-orphan",
        passive_deletes: bool = True,
        order_by: str | None = None,
    ) -> Mapped[list[Any]]:
        """
        Relacionamento **um-para-muitos** (lado "1" possui coleção do modelo filho).

        **Formato de ``target``**

        Igual a ``many_to_one``: ``"app_label.ModelName"``, resolvido via
        ``_resolve_target_to_class``. Com ``foreign_keys`` como lista de strings,
        aplicam-se o descriptor e a validação estrita (possível ``sys.exit(0)`` se
        o formato do ``target`` estiver errado).

        **Parâmetros**

        - ``cascade``: política SQLAlchemy (padrão ``"all, delete-orphan"``).
        - ``passive_deletes``: quando ``True``, deletes em cascata podem ser tratados
          pelo banco (``ON DELETE``) em conjunto com as FKs.
        - ``order_by``: string com nome de coluna no modelo **alvo** para ordenar a
          coleção (repasse ao ``relationship``).

        **Erros:** os mesmos de ``many_to_one`` na resolução do ``target``.

        **Alias:** ``Rel.has_many``.
        """
        if foreign_keys and isinstance(foreign_keys, list) and all(
            isinstance(x, str) for x in foreign_keys
        ):
            kwargs: dict[str, Any] = {
                "back_populates": back_populates,
                "backref": backref,
                "lazy": lazy,
                "cascade": cascade,
                "passive_deletes": passive_deletes,
            }
            if order_by:
                kwargs["order_by"] = order_by
            return _RelationshipDescriptor(
                target,
                "one_to_many",
                kwargs,
                foreign_keys,
            )
        resolved = _resolve_target_to_class(target)
        kwargs = {
            "back_populates": back_populates,
            "backref": backref,
            "lazy": lazy,
            "foreign_keys": foreign_keys,
            "cascade": cascade,
            "passive_deletes": passive_deletes,
        }
        if order_by:
            kwargs["order_by"] = order_by
        return relationship(resolved, **kwargs)
    
    # Alias for Rails users
    has_many = one_to_many
    
    # -------------------------------------------------------------------------
    # One-to-One
    # -------------------------------------------------------------------------
    
    @staticmethod
    def one_to_one(
        target: str,
        *,
        back_populates: str | None = None,
        backref: str | None = None,
        lazy: str = "selectin",
        foreign_keys: list[str] | None = None,
        cascade: str = "all, delete-orphan",
        uselist: bool = False,
    ) -> Mapped[Any]:
        """
        Relacionamento **um-para-um**.

        **Formato de ``target``**

        Como nos outros métodos: ``"app_label.ModelName"``. No modelo que guarda a FK,
        use ``unique=True`` na coluna FK (ou restrição equivalente) para garantir 1:1
        ao nível da base de dados.

        **Implementação:** o ramo com ``foreign_keys`` como lista de strings reutiliza
        o descriptor com ``side="many_to_one"`` (API SQLAlchemy para 1:1 no lado FK).

        **Alias:** ``Rel.has_one``.
        """
        if foreign_keys and isinstance(foreign_keys, list) and all(
            isinstance(x, str) for x in foreign_keys
        ):
            return _RelationshipDescriptor(
                target,
                "many_to_one",
                dict(
                    back_populates=back_populates,
                    backref=backref,
                    lazy=lazy,
                    cascade=cascade,
                    uselist=False,
                ),
                foreign_keys,
            )
        resolved = _resolve_target_to_class(target)
        return relationship(
            resolved,
            back_populates=back_populates,
            backref=backref,
            lazy=lazy,
            foreign_keys=foreign_keys,
            cascade=cascade,
            uselist=False,
        )
    
    # Alias
    has_one = one_to_one
    
    # -------------------------------------------------------------------------
    # Many-to-Many
    # -------------------------------------------------------------------------
    
    @staticmethod
    def many_to_many(
        target: str,
        *,
        secondary: str | Table,
        back_populates: str | None = None,
        backref: str | None = None,
        lazy: str = "selectin",
        cascade: str = "all",
        passive_deletes: bool = True,
        order_by: str | None = None,
    ) -> Mapped[list[Any]]:
        """
        Relacionamento **muitos-para-muitos** com tabela ``secondary``.

        **Formato de ``target``**

        - ``"app_label.ModelName"`` do outro extremo da associação (o mesmo padrão
          que ``_resolve_target_to_class``).

        **Parâmetro ``secondary``**

        - ``str``: nome da tabela. Se existir em ``AssociationTable`` (criada antes com
          ``AssociationTable.create``), a instância em cache é usada; caso contrário o
          SQLAlchemy trata a string conformo o metadata do registry.
        - ``Table``: objeto ``sqlalchemy.Table`` (ex.: retorno de ``AssociationTable.create``).

        A tabela de junção deve declarar FKs para **ambas** as entidades (tipicamente
        chave composta com as duas FKs).

        **Parâmetros adicionais:** ``cascade``, ``passive_deletes``, ``order_by`` —
        mesmo espírito que em ``one_to_many``.
        """
        # If secondary is a string, try to get it from cache or use as-is
        if isinstance(secondary, str):
            cached_table = AssociationTable.get(secondary)
            if cached_table is not None:
                secondary = cached_table
        
        resolved = _resolve_target_to_class(target)
        kwargs: dict[str, Any] = {
            "secondary": secondary,
            "back_populates": back_populates,
            "backref": backref,
            "lazy": lazy,
            "cascade": cascade,
            "passive_deletes": passive_deletes,
        }
        
        if order_by:
            kwargs["order_by"] = order_by
        
        return relationship(resolved, **kwargs)
    
    # -------------------------------------------------------------------------
    # Self-referential relationships
    # -------------------------------------------------------------------------
    
    @staticmethod
    def self_referential(
        *,
        back_populates: str | None = None,
        remote_side: str | None = None,
        lazy: str = "selectin",
        cascade: str = "all",
        foreign_keys: str | None = None,
        uselist: bool = True,
    ) -> Mapped[Any]:
        """
        ``relationship`` na **mesma classe** (hierarquia, árvore, grafo sobre uma tabela).

        **Parâmetros (nomes de atributos na classe)**

        - ``foreign_keys``: string com o **nome do atributo** Python da coluna FK
          (ex.: ``"parent_id"``), não ``"Category.parent_id"``.
        - ``remote_side``: string com o **nome do atributo** do lado "pai"
          (normalmente ``"id"``).
        - ``uselist``: ``True`` para coleção de filhos (1:N), ``False`` para referência
          ao pai (N:1).

        Quando ``foreign_keys`` ou ``remote_side`` são strings, usa-se
        ``_SelfReferentialDescriptor`` para converter nomes em objetos ``Column``.

        **Validação:** não passa por ``app_label.ModelName``; o alvo é sempre a
        própria classe.

        Exemplo::

            class Category(Model):
                __tablename__ = "categories"
                id: Mapped[int] = Field.pk()
                name: Mapped[str] = Field.string(max_length=100)
                parent_id: Mapped[int | None] = Rel.foreign_key(
                    "categories.id", nullable=True, ondelete="SET NULL",
                )
                children: Mapped[list["Category"]] = Rel.self_referential(
                    back_populates="parent", foreign_keys="parent_id",
                )
                parent: Mapped["Category | None"] = Rel.self_referential(
                    back_populates="children", remote_side="id", uselist=False,
                )

        Relações auto-referenciadas complexas podem exigir ``relationship()`` directo
        do SQLAlchemy com ``remote_side`` / ``foreign_keys`` mais explícitos.
        """
        # Note: This is a simplified helper. For complex self-referential
        # relationships, you may need to use relationship() directly with
        # proper remote_side configuration.
        if (foreign_keys and isinstance(foreign_keys, str)) or (
            remote_side and isinstance(remote_side, str)
        ):
            return _SelfReferentialDescriptor(
                back_populates=back_populates,
                lazy=lazy,
                cascade=cascade,
                uselist=uselist,
                foreign_keys=foreign_keys,
                remote_side=remote_side,
            )
        kwargs: dict[str, Any] = {
            "back_populates": back_populates,
            "lazy": lazy,
            "cascade": cascade,
            "uselist": uselist,
        }
        if remote_side:
            kwargs["remote_side"] = remote_side
        if foreign_keys:
            kwargs["foreign_keys"] = foreign_keys
        return relationship(
            kwargs.pop("back_populates", None) and "self" or None, **kwargs
        )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "Rel",
    "AssociationTable",
    "clear_model_cache",
]
