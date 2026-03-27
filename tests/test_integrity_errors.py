"""Testes para respostas seguras de erros de integridade."""

from strider.integrity_errors import SafeIntegrityBody, safe_body_from_integrity_error


class _FakeIntegrity:
    """Mínimo para simular sqlalchemy.exc.IntegrityError.orig."""

    def __init__(self, orig: str | None):
        self.orig = orig


def test_pg_foreign_key_safe_response():
    msg = (
        'insert or update on table "bugs_models" violates foreign key constraint '
        '"bugs_models_author_id_fkey"\n'
        'DETAIL:  Key (author_id)=(2) is not present in table "users".'
    )
    exc = _FakeIntegrity(msg)
    body = safe_body_from_integrity_error(exc, log_full=False)
    assert isinstance(body, SafeIntegrityBody)
    assert body.code == "foreign_key_violation"
    assert body.status_code == 400
    assert body.field == "author_id"
    assert "debug" not in body.as_dict()
    assert "users" not in body.detail
    d = body.as_dict()
    assert "hint" in d


def test_sqlite_unique():
    exc = _FakeIntegrity("UNIQUE constraint failed: bugs_models.title")
    body = safe_body_from_integrity_error(exc, log_full=False)
    assert body.code == "unique_constraint"
    assert body.status_code == 409


def test_generic_no_raw_sql_in_payload():
    exc = _FakeIntegrity("some obscure db error xyz")
    body = safe_body_from_integrity_error(exc, log_full=False)
    assert body.code == "integrity_error"
    assert "xyz" not in body.as_dict().values()
    assert "obscure" not in str(body.as_dict())
