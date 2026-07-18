from backend import privacy, proof
from backend.repositories.privacy_repository import JsonPrivacyRepository
from backend.repositories.proof_repository import JsonProofRepository


def test_privacy_store_requires_users_dict(monkeypatch, tmp_path):
    repository = JsonPrivacyRepository(tmp_path / "privacy.json")
    repository.store.save([])
    monkeypatch.setattr(privacy, "get_privacy_repository", lambda: repository)

    assert privacy.load_privacy() == {"users": {}}


def test_privacy_update_persists_user_settings(monkeypatch, tmp_path):
    repository = JsonPrivacyRepository(tmp_path / "privacy.json")
    monkeypatch.setattr(privacy, "get_privacy_repository", lambda: repository)

    settings = privacy.update_user_privacy("user@example.com", "allow_messages", False)

    assert settings["allow_messages"] is False
    assert privacy.get_user_privacy("user@example.com")["allow_messages"] is False


def test_proof_store_requires_proofs_list(monkeypatch, tmp_path):
    repository = JsonProofRepository(tmp_path / "proofs.json")
    repository.store.save({"proofs": {}})
    monkeypatch.setattr(proof, "get_proof_repository", lambda: repository)

    assert proof.load_proofs() == {"proofs": []}


def test_proof_store_saves_proofs(monkeypatch, tmp_path):
    repository = JsonProofRepository(tmp_path / "proofs.json")
    monkeypatch.setattr(proof, "get_proof_repository", lambda: repository)

    proof.save_proofs({"proofs": [{"email": "user@example.com"}]})

    assert proof.load_proofs() == {"proofs": [{"email": "user@example.com"}]}
