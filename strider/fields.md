# Campos e StructSchema nas models

Este documento descreve como usar **StructSchema** em models do Strider: tipagem, uso em atributos e como as migrações tratam esses campos.

---

## 1. O que é StructSchema

`StructSchema` é um sistema de schemas estruturados para colunas JSON: você define uma classe com campos tipados (StringField, BooleanField, NestedField, etc.) e usa essa classe em um campo da model. O valor no banco é um JSON; na aplicação você pode validar, usar defaults e migrar dados antigos (aliases, campos faltando).

- **Banco**: coluna JSON (PostgreSQL: JSONB; SQLite/MySQL: JSON) via `AdaptiveJSON`.
- **Python**: o valor lido/escrito na coluna é um **dict**. Para acesso tipado, use `SeuSchema.from_dict_safe(instancia.campo)` e, ao salvar, `instancia.campo = obj.to_dict()` ou atribua um dict (parcial ou completo).

---

## 2. Definir um StructSchema

Em `strider.schema` você tem os tipos de campo: `StringField`, `IntegerField`, `FloatField`, `BooleanField`, `ListField`, `NestedField`, `DictField`, `ChoiceField`.

Exemplo:

```python
from strider.schema import StructSchema, StringField, BooleanField, NestedField

class UserPreferences(StructSchema):
    theme = StringField(default="system", choices=["light", "dark", "system"])
    language = StringField(default="pt-BR", aliases=["lang"])  # "lang" → language
    notifications = NestedField({
        "email": BooleanField(default=True),
        "push": BooleanField(default=True),
    })
```

- **default**: valor padrão quando o campo falta no JSON.
- **choices**: validação para valores permitidos (ex.: tema).
- **aliases**: nomes antigos no JSON mapeados para o nome do campo (ex.: `"lang"` → `language`), útil para migração de dados.
- **NestedField**: objeto aninhado; pode ser um dict de `Field` ou uma classe `StructSchema`.

---

## 3. Usar na model (tipado)

Use **`Field.struct(SeuSchema)`** nas models (em `strider.models`). Isso cria uma coluna `AdaptiveJSON` com `info={"struct_schema": SeuSchema}`.

Exemplo com tipagem:

```python
from strider.models import Model, Field
from strider.schema import StructSchema, StringField, BooleanField, NestedField
from sqlalchemy.orm import Mapped

class UserPreferences(StructSchema):
    theme = StringField(default="system", choices=["light", "dark", "system"])
    language = StringField(default="pt-BR", aliases=["lang"])
    notifications = NestedField({
        "email": BooleanField(default=True),
        "push": BooleanField(default=True),
    })

class User(Model):
    __tablename__ = "users"
    id: Mapped[int] = Field.pk()
    preferences: Mapped[dict] = Field.struct(UserPreferences)  # banco guarda dict
```

Anotação sugerida: `Mapped[dict]`, pois o valor na coluna é um dict. Para uso tipado na aplicação, converta com o schema:

```python
# Leitura: dict → StructSchema (acesso tipado)
prefs = UserPreferences.from_dict_safe(user.preferences)
assert prefs.theme == "system"
assert prefs.notifications["email"] is True

# Atribuição por atributo (com validação)
prefs.theme = "dark"  # valida choices
user.preferences = prefs.to_dict()

# Ou atribuir dict (parcial ou completo); ao salvar, normaliza via schema
user.preferences = {"theme": "dark", "lang": "en"}
```

**Default**: se não passar `default` em `Field.struct()`, o valor inicial é `UserPreferences.default_dict()` (dict com defaults do schema). Pode passar `default=...` (dict ou instância do schema).

**Nullable / index**:

```python
preferences: Mapped[dict | None] = Field.struct(UserPreferences, nullable=True)
settings: Mapped[dict] = Field.struct(Settings, index=True)  # GIN no PostgreSQL
```

---

## 4. AdvancedField.struct (strider.fields)

`AdvancedField.struct()` faz o mesmo tipo de coluna (AdaptiveJSON + `struct_schema` no `info`), mas não integra descriptor. Para models, prefira **`Field.struct()`** em `strider.models`.

---

## 5. Migrações

- O campo é mapeado como coluna **AdaptiveJSON**.
- O estado da migration usa o nome do tipo **ADAPTIVEJSON** (via `get_sqlalchemy_type_string` em `strider.migrations.state`).
- **Equivalência de tipos**: em `state.EQUIVALENT_TYPES`, `JSON`, `JSONB` e `ADAPTIVEJSON` são tratados como equivalentes. Ou seja, não se gera alteração de tipo ao mudar entre JSON/JSONB/AdaptiveJSON.
- **Dialetos**:
  - **PostgreSQL**: `ADAPTIVEJSON` → **JSONB** (permite índice GIN se `index=True`).
  - **SQLite / MySQL**: `ADAPTIVEJSON` → **JSON**.

Ou seja: ao adicionar ou alterar um campo `Field.struct(SeuSchema)`, o analisador de migrações vê uma coluna JSON/JSONB; as migrações geradas criam/alteram a coluna como JSON (ou JSONB no PostgreSQL). O conteúdo interno do JSON não é alterado pelas migrações de schema; a “migração” de dados antigos (campos novos, renomeações) é feita em tempo de leitura pelo StructSchema (defaults, aliases, `from_dict_safe`).

---

## 6. Resumo

| Aspecto | Detalhe |
|--------|---------|
| Definição | Classe herda de `StructSchema` com atributos = `StringField`, `BooleanField`, `NestedField`, etc. |
| Na model | `campo: Mapped[dict] = Field.struct(SeuSchema)` (ou `Mapped[dict \| None]` se `nullable=True`) |
| Valor na coluna | Sempre **dict** (JSON). |
| Acesso tipado | `SeuSchema.from_dict_safe(instancia.campo)` para obter objeto com atributos; ao salvar: `instancia.campo = obj.to_dict()` ou dict. |
| Default | `SeuSchema.default_dict()` se não informar `default` em `Field.struct()`. |
| Migrações | Coluna como JSON/JSONB (AdaptiveJSON → JSONB no PostgreSQL, JSON nos demais). Sem mudança de dados; compatibilidade com dados antigos via defaults e aliases no schema. |
| Admin | Colunas com `info.struct_schema` usam o widget `struct_editor` no admin. |
| Filtros | Lookups tipo `preferences__theme__exact="dark"` funcionam como em outros campos JSON (querysets usam `struct_schema` no `info` para tratar como JSON). |

---

## 7. Referência rápida dos campos do schema

- **StringField**: default, max_length, choices, regex, nullable, aliases  
- **IntegerField / FloatField**: default, min_value, max_value, nullable, aliases  
- **BooleanField**: default, nullable, aliases  
- **ListField**: default, item_field, nullable  
- **NestedField**: dict de campos ou classe StructSchema; default, nullable, aliases  
- **DictField**: default, nullable  
- **ChoiceField**: choices, default, nullable  

Todos suportam **aliases** para mapear nomes antigos no JSON para o nome do campo (migração suave de dados).
