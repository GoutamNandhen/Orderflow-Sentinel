import uuid
import pytest
from backend import auth
from backend.db import transaction
from backend.models import ModelArtifact, Setting
from backend.services import core

def test_local_operator_credential_is_private_and_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, 'DATA', tmp_path)
    monkeypatch.delenv('OPERATOR_PASSWORD', raising=False)
    monkeypatch.setenv('ENVIRONMENT', 'development')
    first = auth.operator_password()
    assert len(first) >= 32
    assert auth.operator_password() == first
    assert (tmp_path/'operator-password.local').is_file()

def test_hosted_startup_requires_explicit_private_credential(monkeypatch):
    monkeypatch.delenv('OPERATOR_PASSWORD', raising=False)
    monkeypatch.setenv('ENVIRONMENT', 'production')
    with pytest.raises(RuntimeError, match='private hosting environment'):
        auth.operator_password()

def test_configured_operator_credential_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, 'DATA', tmp_path)
    configured = uuid.uuid4().hex
    monkeypatch.setenv('OPERATOR_PASSWORD', configured)
    assert auth.operator_password() == configured
    assert not (tmp_path/'operator-password.local').exists()

def test_database_backed_model_artifact_restores_after_restart(client, tmp_path, monkeypatch):
    version = 'verified-artifact-restore-fixture'
    with transaction() as s:
        s.add(ModelArtifact(version=version, bundle=b'isolated-model-fixture', report={'version':version}))
        s.add(Setting(key='active_model_version', value={'version':version}))
    monkeypatch.setattr(core, 'DATA', tmp_path)
    core.initialize()
    assert (tmp_path/'models'/f'{version}.joblib').read_bytes() == b'isolated-model-fixture'
    assert (tmp_path/'models'/'current.txt').read_text() == version
