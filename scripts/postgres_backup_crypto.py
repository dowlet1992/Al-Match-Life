#!/usr/bin/env python3
"""Stream-encrypt NOVIX PostgreSQL archives with authenticated AES-256-GCM."""

import argparse
import base64
import binascii
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


MAGIC = b"NOVIXBK1"
NONCE_BYTES = 12
TAG_BYTES = 16
CHUNK_BYTES = 1024 * 1024


class BackupCryptoError(RuntimeError):
    pass


def load_backup_key(environ=None):
    environ = os.environ if environ is None else environ
    encoded = str(environ.get("NOVIX_BACKUP_ENCRYPTION_KEY", "")).strip()
    if not encoded:
        raise BackupCryptoError("NOVIX_BACKUP_ENCRYPTION_KEY is required")
    try:
        key = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BackupCryptoError("NOVIX_BACKUP_ENCRYPTION_KEY must be valid Base64") from exc
    if len(key) != 32:
        raise BackupCryptoError("NOVIX_BACKUP_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return key


def _safe_output_path(source, output, suffix):
    source = Path(source).resolve()
    output = Path(output).resolve() if output else Path(f"{source}{suffix}")
    if source == output:
        raise BackupCryptoError("Source and output paths must be different")
    output.parent.mkdir(parents=True, exist_ok=True)
    return source, output


def encrypt_archive(source, output=None, *, key=None, environ=None, overwrite=False):
    source, output = _safe_output_path(source, output, ".enc")
    if not source.is_file():
        raise BackupCryptoError("Backup archive does not exist")
    if output.exists() and not overwrite:
        raise BackupCryptoError("Encrypted output already exists")
    key = key or load_backup_key(environ)
    nonce = os.urandom(NONCE_BYTES)
    partial = output.with_name(f".{output.name}.partial")
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(MAGIC)
    try:
        with source.open("rb") as plaintext, partial.open("wb") as encrypted:
            encrypted.write(MAGIC)
            encrypted.write(nonce)
            for chunk in iter(lambda: plaintext.read(CHUNK_BYTES), b""):
                encrypted.write(encryptor.update(chunk))
            encrypted.write(encryptor.finalize())
            encrypted.write(encryptor.tag)
        partial.chmod(0o600)
        os.replace(partial, output)
    finally:
        partial.unlink(missing_ok=True)
    return output


def decrypt_archive(source, output, *, key=None, environ=None, overwrite=False):
    source, output = _safe_output_path(source, output, ".decrypted")
    if not source.is_file():
        raise BackupCryptoError("Encrypted backup does not exist")
    if output.exists() and not overwrite:
        raise BackupCryptoError("Decrypted output already exists")
    size = source.stat().st_size
    if size < len(MAGIC) + NONCE_BYTES + TAG_BYTES:
        raise BackupCryptoError("Encrypted backup is truncated")
    key = key or load_backup_key(environ)
    partial = output.with_name(f".{output.name}.partial")
    try:
        with source.open("rb") as encrypted:
            if encrypted.read(len(MAGIC)) != MAGIC:
                raise BackupCryptoError("Encrypted backup header is invalid")
            nonce = encrypted.read(NONCE_BYTES)
            encrypted.seek(-TAG_BYTES, os.SEEK_END)
            tag = encrypted.read(TAG_BYTES)
            remaining = size - len(MAGIC) - NONCE_BYTES - TAG_BYTES
            encrypted.seek(len(MAGIC) + NONCE_BYTES)
            decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(MAGIC)
            try:
                with partial.open("wb") as plaintext:
                    while remaining:
                        chunk = encrypted.read(min(CHUNK_BYTES, remaining))
                        if not chunk:
                            raise BackupCryptoError("Encrypted backup is truncated")
                        remaining -= len(chunk)
                        plaintext.write(decryptor.update(chunk))
                    plaintext.write(decryptor.finalize())
            except InvalidTag as exc:
                raise BackupCryptoError("Encrypted backup authentication failed") from exc
        partial.chmod(0o600)
        os.replace(partial, output)
    finally:
        partial.unlink(missing_ok=True)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="Encrypt or decrypt a NOVIX PostgreSQL backup archive.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    encrypt = subparsers.add_parser("encrypt")
    encrypt.add_argument("source")
    encrypt.add_argument("--output")
    encrypt.add_argument("--overwrite", action="store_true")
    decrypt = subparsers.add_parser("decrypt")
    decrypt.add_argument("source")
    decrypt.add_argument("--output", required=True)
    decrypt.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "encrypt":
            output = encrypt_archive(args.source, args.output, overwrite=args.overwrite)
        else:
            output = decrypt_archive(args.source, args.output, overwrite=args.overwrite)
    except BackupCryptoError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "output": str(output), "bytes": output.stat().st_size}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
