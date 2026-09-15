import base64
import os

import pytest

from scripts.postgres_backup_crypto import (
    BackupCryptoError,
    MAGIC,
    decrypt_archive,
    encrypt_archive,
    load_backup_key,
)


def test_backup_encryption_round_trip_is_private_and_stream_safe(tmp_path):
    key = os.urandom(32)
    source = tmp_path / "novix.dump"
    source.write_bytes(os.urandom(2 * 1024 * 1024 + 37))

    encrypted = encrypt_archive(source, key=key)
    restored = decrypt_archive(encrypted, tmp_path / "restored.dump", key=key)

    assert encrypted.read_bytes().startswith(MAGIC)
    assert encrypted.read_bytes() != source.read_bytes()
    assert restored.read_bytes() == source.read_bytes()
    assert encrypted.stat().st_mode & 0o777 == 0o600
    assert restored.stat().st_mode & 0o777 == 0o600


def test_backup_decryption_rejects_wrong_key_and_removes_partial_file(tmp_path):
    source = tmp_path / "novix.dump"
    source.write_bytes(b"database" * 200)
    encrypted = encrypt_archive(source, key=os.urandom(32))
    output = tmp_path / "restored.dump"

    with pytest.raises(BackupCryptoError, match="authentication failed"):
        decrypt_archive(encrypted, output, key=os.urandom(32))

    assert not output.exists()
    assert not (tmp_path / ".restored.dump.partial").exists()


def test_backup_key_requires_base64_encoded_32_bytes():
    key = os.urandom(32)
    assert load_backup_key({"NOVIX_BACKUP_ENCRYPTION_KEY": base64.b64encode(key).decode()}) == key
    with pytest.raises(BackupCryptoError):
        load_backup_key({})
    with pytest.raises(BackupCryptoError):
        load_backup_key({"NOVIX_BACKUP_ENCRYPTION_KEY": "not-base64"})
    with pytest.raises(BackupCryptoError):
        load_backup_key({"NOVIX_BACKUP_ENCRYPTION_KEY": base64.b64encode(b"short").decode()})


def test_backup_crypto_never_overwrites_existing_output(tmp_path):
    source = tmp_path / "novix.dump"
    source.write_bytes(b"database" * 200)
    output = tmp_path / "novix.dump.enc"
    output.write_bytes(b"keep")

    with pytest.raises(BackupCryptoError, match="already exists"):
        encrypt_archive(source, output, key=os.urandom(32))

    assert output.read_bytes() == b"keep"
