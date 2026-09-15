import os

from cryptography.fernet import Fernet, InvalidToken


ENCRYPTED_FILE_PREFIX = b"AML1:"


class DataEncryptionError(RuntimeError):
    pass


def configured_cipher(environ=None):
    environ = os.environ if environ is None else environ
    key = str(environ.get("DATA_ENCRYPTION_KEY", "")).strip()
    if not key:
        return None
    try:
        return Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as error:
        raise DataEncryptionError(
            "DATA_ENCRYPTION_KEY must be a valid Fernet key; generate one with Fernet.generate_key()."
        ) from error


def encrypt_bytes(payload, environ=None):
    cipher = configured_cipher(environ)
    if cipher is None:
        return payload
    return ENCRYPTED_FILE_PREFIX + cipher.encrypt(payload)


def decrypt_bytes(payload, environ=None):
    if not payload.startswith(ENCRYPTED_FILE_PREFIX):
        return payload
    cipher = configured_cipher(environ)
    if cipher is None:
        raise DataEncryptionError("DATA_ENCRYPTION_KEY is required to read encrypted application data.")
    try:
        return cipher.decrypt(payload[len(ENCRYPTED_FILE_PREFIX):])
    except InvalidToken as error:
        raise DataEncryptionError("Application data could not be authenticated or decrypted.") from error
