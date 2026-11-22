"""Envelope encryption for the HR vault (AES-256-GCM).

* Every file gets its own random 256-bit data key (DEK).
* The file bytes (and its extracted text) are encrypted with the DEK.
* The DEK is "wrapped" (encrypted) with the master key (KEK) and stored next to the metadata.
* The master key is never in the code or the database: it is read from VAULT_MASTER_KEY
  (base64) or from the file at VAULT_MASTER_KEY_FILE, which lives on a separate volume.
"""
import base64
import hashlib
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger("leaddesk.crypto")
MAGIC = b"LDV1"  # file header so a stored blob is recognisable (and visibly not a PDF/JPEG)
_KEK: bytes | None = None


def _default_key_file():
    return os.environ.get("VAULT_MASTER_KEY_FILE") or os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "secrets", "vault_master.key")


def load_master_key() -> bytes:
    global _KEK
    if _KEK:
        return _KEK
    env = os.environ.get("VAULT_MASTER_KEY")
    if env:
        key = base64.b64decode(env)
    else:
        path = _default_key_file()
        if not os.path.exists(path):
            if os.environ.get("VAULT_AUTOCREATE_KEY", "1") != "1":
                raise RuntimeError(f"Vault master key not found at {path}")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(base64.b64encode(os.urandom(32)))
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            log.warning("Generated a new vault master key at %s - back it up; without it the vault is unreadable.", path)
        with open(path, "rb") as f:
            key = base64.b64decode(f.read().strip())
    if len(key) != 32:
        raise RuntimeError("Vault master key must be 32 bytes (AES-256)")
    _KEK = key
    return key


def key_fingerprint() -> str:
    return hashlib.sha256(load_master_key()).hexdigest()[:16]


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def _open(key: bytes, blob: bytes, aad: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


def new_file_key() -> tuple[bytes, bytes]:
    """Returns (dek, wrapped_dek)."""
    dek = AESGCM.generate_key(bit_length=256)
    return dek, _seal(load_master_key(), dek, b"dek")


def unwrap(wrapped: bytes) -> bytes:
    return _open(load_master_key(), wrapped, b"dek")


def encrypt_blob(dek: bytes, data: bytes, aad: str) -> bytes:
    return MAGIC + _seal(dek, data, aad.encode())


def decrypt_blob(dek: bytes, blob: bytes, aad: str) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("Not a vault blob")
    return _open(dek, blob[len(MAGIC):], aad.encode())
