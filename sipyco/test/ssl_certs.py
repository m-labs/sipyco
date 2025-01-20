import os
import subprocess

from sipyco.tools import SimpleSSLConfig


def create_ssl_certs(cert_dir):
    for cert_name in ["server", "client"]:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa",
            "-keyout", os.path.join(cert_dir, f"{cert_name}.key"),
            "-nodes",
            "-out", os.path.join(cert_dir, f"{cert_name}.pem"),
            "-sha256",
            "-subj", "/"
        ], check=True)

    certs = {
        "server_key": os.path.join(cert_dir, "server.key"),
        "server_cert": os.path.join(cert_dir, "server.pem"),
        "client_key": os.path.join(cert_dir, "client.key"),
        "client_cert": os.path.join(cert_dir, "client.pem"),
    }

    return certs


def create_ssl_config(role, certs):
    if role == "server":
        ssl_config = SimpleSSLConfig(certs["server_cert"], certs["server_key"], certs["client_cert"])
    elif role == "client":
        ssl_config = SimpleSSLConfig(certs["client_cert"], certs["client_key"], certs["server_cert"])
    return ssl_config
