from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


CA_KEY_FILE = "vm-builder-ca.key"
CA_CERT_FILE = "vm-builder-ca.crt"
CLIENT_KEY_FILE = "vm-builder-apiserver.key"
CLIENT_CERT_FILE = "vm-builder-apiserver.crt"


class PKIError(Exception):
    pass


def _write_private_key(path: Path, key: ec.EllipticCurvePrivateKey):
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def _write_cert(path: Path, cert: x509.Certificate):
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    path.chmod(0o644)


def _load_private_key(path: Path):
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _load_cert(path: Path):
    return x509.load_pem_x509_certificate(path.read_bytes())


def _require_complete_pair(key_path: Path, cert_path: Path, label: str):
    key_exists = key_path.exists()
    cert_exists = cert_path.exists()
    if key_exists != cert_exists:
        raise PKIError(
            f"partial {label} state in {key_path.parent}: expected both "
            f"{key_path.name} and {cert_path.name} or neither"
        )
    return key_exists and cert_exists


def ensure(pki_dir: str, ca_common_name: str = "vm-builder-ca",
           client_common_name: str = "vm-builder-apiserver") -> dict[str, str]:
    directory = Path(pki_dir)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)

    ca_key_path = directory / CA_KEY_FILE
    ca_cert_path = directory / CA_CERT_FILE
    client_key_path = directory / CLIENT_KEY_FILE
    client_cert_path = directory / CLIENT_CERT_FILE

    if _require_complete_pair(ca_key_path, ca_cert_path, "CA"):
        ca_key = _load_private_key(ca_key_path)
        ca_cert = _load_cert(ca_cert_path)
    else:
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca_subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, ca_common_name),
        ])
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_subject)
            .issuer_name(ca_subject)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=False,
                    key_encipherment=False,
                    key_cert_sign=True,
                    key_agreement=False,
                    content_commitment=False,
                    data_encipherment=False,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )
        _write_private_key(ca_key_path, ca_key)
        _write_cert(ca_cert_path, ca_cert)

    if not _require_complete_pair(client_key_path, client_cert_path, "client cert"):
        client_key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(timezone.utc)
        client_cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, client_common_name)]))
            .issuer_name(ca_cert.subject)
            .public_key(client_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=365 * 5))
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=False,
                    key_cert_sign=False,
                    key_agreement=False,
                    content_commitment=False,
                    data_encipherment=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        _write_private_key(client_key_path, client_key)
        _write_cert(client_cert_path, client_cert)

    return {
        "ca_key": str(ca_key_path),
        "ca_cert": str(ca_cert_path),
        "client_key": str(client_key_path),
        "client_cert": str(client_cert_path),
    }
