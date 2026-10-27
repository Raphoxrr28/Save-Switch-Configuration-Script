#!/usr/bin/env python3
"""Back up network-device configurations listed in an inventory CSV."""

from __future__ import annotations

import argparse
import csv
import getpass
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


DATE_FORMAT = "%Y-%m-%d_%H-%M-%S"
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:_|$)")

# Each profile selects the Netmiko driver, display name, command, and
# configuration signature used to reject login banners or command errors.
PLATFORMS: dict[str, dict[str, str]] = {
    "ciscoios": {
        "manufacturer": "Cisco",
        "device_type": "cisco_ios",
        "command": "show running-config",
        "config_pattern": r"(?im)^\s*hostname\s+\S+",
    },
    "hp1920": {
        "manufacturer": "HP",
        "device_type": "hp_comware",
        "command": "display current-configuration",
        "config_pattern": r"(?im)^\s*sysname\s+\S+",
    },
    # Generic Aruba selects ArubaOS-Switch. Use ArubaOS-CX explicitly for CX.
    "aruba": {
        "manufacturer": "Aruba",
        "device_type": "aruba_osswitch",
        "command": "show running-config",
        "config_pattern": r"(?im)^\s*(?:hostname\s+\S+|;\s*.*configuration editor)",
    },
    "arubaos-cx": {
        "manufacturer": "Aruba",
        "device_type": "aruba_aoscx",
        "command": "show running-config",
        "config_pattern": r"(?im)^\s*(?:hostname\s+\S+|;\s*.*configuration editor)",
    },
    "arubaos-switch": {
        "manufacturer": "Aruba",
        "device_type": "aruba_osswitch",
        "command": "show running-config",
        "config_pattern": r"(?im)^\s*(?:hostname\s+\S+|;\s*.*configuration editor)",
    },
    "hpprocurve": {
        "manufacturer": "HP",
        "device_type": "hp_procurve",
        "command": "show running-config",
        "config_pattern": r"(?im)^\s*(?:hostname\s+\S+|;\s*.*configuration editor)",
    },
}


def sanitize_filename_part(value: str) -> str:
    """Replace characters Windows does not allow in file and folder names."""
    return INVALID_FILENAME_CHARS.sub("_", value)


def read_inventory(inventory_path: Path) -> list[dict[str, str]]:
    """Load and validate required columns from the CSV inventory."""
    with inventory_path.open("r", encoding="utf-8-sig", newline="") as inventory_file:
        reader = csv.DictReader(inventory_file)
        if reader.fieldnames is None:
            raise ValueError(f"Inventaire vide ou sans en-tête : {inventory_path}")

        missing_columns = {"Host", "Platform"} - set(reader.fieldnames)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Le CSV doit contenir les colonnes Host et Platform. Manquante(s) : {missing}")

        devices = [
            {key: (value or "").strip() for key, value in row.items() if key is not None}
            for row in reader
            if any(value and value.strip() for value in row.values() if value is not None)
        ]

    if not devices:
        raise ValueError(f"Inventaire vide : {inventory_path}")

    for row_number, device in enumerate(devices, start=2):
        if not device.get("Host"):
            raise ValueError(f"Adresse Host manquante à la ligne {row_number} de l'inventaire.")
        if not device.get("Platform"):
            device["Platform"] = "CiscoIOS"
        if device["Platform"].casefold() not in PLATFORMS:
            raise ValueError(f"Plateforme non prise en charge : {device['Platform']}")

    return devices


def remove_expired_backups(backup_folder: Path) -> None:
    """Delete dated backup directories older than 30 days, without following links."""
    cutoff = datetime.now() - timedelta(days=30)
    if not backup_folder.is_dir():
        return

    for old_backup in backup_folder.iterdir():
        is_junction = getattr(old_backup, "is_junction", lambda: False)
        if old_backup.is_symlink() or is_junction() or not old_backup.is_dir():
            continue
        match = DATE_PREFIX.match(old_backup.name)
        if not match:
            continue

        try:
            backup_date = datetime.strptime(match.group(1), DATE_FORMAT)
        except ValueError:
            continue

        if backup_date < cutoff:
            shutil.rmtree(old_backup)
            print(f"[SUPPRIME] Sauvegarde de plus de 30 jours : {old_backup.name}")


def fetch_configuration(
    device: dict[str, str],
    profile: dict[str, str],
    username: str,
    password: str,
    port: int,
) -> str:
    """Connect with Netmiko and retrieve the running configuration."""
    try:
        from netmiko import ConnectHandler
        from netmiko.exceptions import NetmikoBaseException
        from paramiko.ssh_exception import SSHException
    except ImportError as error:
        raise RuntimeError(
            "Netmiko n'est pas installé. Installez les dépendances avec "
            "'python -m pip install -r requirements.txt'."
        ) from error

    connection_args: dict[str, Any] = {
        "device_type": profile["device_type"],
        "host": device["Host"],
        "username": username,
        "password": password,
        "port": port,
        "conn_timeout": 15,
        "auth_timeout": 15,
        "banner_timeout": 15,
        "fast_cli": False,
        # Require a host key already trusted in the user's known_hosts file.
        "ssh_strict": True,
        "system_host_keys": True,
    }

    try:
        with ConnectHandler(**connection_args) as connection:
            if device["Platform"].casefold() == "hp1920":
                # Some HP 1920 models require this command before showing the full CLI.
                response = connection.send_command_timing("_cmdline-mode on")
                if re.search(r"(?i)(?:\[y/n\]|\(y/n\)|continue.*[y/n])", response):
                    connection.send_command_timing("y")
                connection.send_command_timing("screen-length disable")
                configuration = connection.send_command_timing(
                    profile["command"],
                    read_timeout=120,
                    last_read=3,
                )
            else:
                configuration = connection.send_command(
                    profile["command"],
                    read_timeout=120,
                )
    except (NetmikoBaseException, SSHException, OSError, ValueError) as error:
        raise RuntimeError(f"Erreur de connexion ou de commande SSH : {error}") from error

    return configuration.strip()


def run(inventory_path: Path, backup_folder: Path) -> int:
    """Back up every listed device and return a process exit code."""
    devices = read_inventory(inventory_path)
    remove_expired_backups(backup_folder)

    run_timestamp = datetime.now().strftime(DATE_FORMAT)
    success_count = 0
    failures: list[tuple[str, str]] = []

    for device in devices:
        name = device.get("Name") or device["Host"]
        port_text = device.get("Port") or "22"

        try:
            port = int(port_text)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError as error:
            message = f"Port SSH invalide : {port_text}"
            print(f"[ECHEC] {name} : {message}", file=sys.stderr)
            failures.append((name, message))
            continue

        username = device.get("User") or input(f"Utilisateur SSH pour {name} : ").strip()
        if not username:
            message = "Le nom d'utilisateur SSH ne peut pas être vide."
            print(f"[ECHEC] {name} : {message}", file=sys.stderr)
            failures.append((name, message))
            continue

        password = getpass.getpass(f"Mot de passe SSH pour {username}@{device['Host']} : ")
        if not password:
            message = "Le mot de passe SSH ne peut pas être vide."
            print(f"[ECHEC] {name} : {message}", file=sys.stderr)
            failures.append((name, message))
            continue

        platform = device.get("Platform") or "CiscoIOS"
        profile = PLATFORMS[platform.casefold()]

        try:
            configuration = fetch_configuration(device, profile, username, password, port)
            if not configuration:
                raise RuntimeError("Connexion SSH réussie, mais la configuration est vide.")
            if re.search(profile["config_pattern"], configuration) is None:
                raise RuntimeError(
                    f"La sortie SSH ne contient pas la configuration attendue pour {platform}."
                )

            safe_host = sanitize_filename_part(device["Host"])
            device_folder = backup_folder / (
                f"{run_timestamp}_{profile['manufacturer']}_{safe_host}"
            )
            device_folder.mkdir(parents=True, exist_ok=True)
            filename = f"{sanitize_filename_part(name)}_{safe_host}.txt"
            (device_folder / filename).write_text(
                configuration + "\n",
                encoding="utf-8",
            )
            print(f"[OK] {name} : {device_folder}")
            success_count += 1
        except (OSError, RuntimeError, ValueError) as error:
            message = str(error)
            print(f"[ECHEC] {name} : {message}", file=sys.stderr)
            failures.append((name, message))

    print(f"Sauvegardes dans : {backup_folder}")
    print(
        f"Bilan : {success_count} réussite(s), {len(failures)} échec(s) "
        f"sur {len(devices)}."
    )
    for name, message in failures:
        print(f" - {name} : {message}")

    return 1 if failures else 0


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options, defaulting paths to this script's folder."""
    project_folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Sauvegarde les configurations des équipements du CSV via SSH."
    )
    parser.add_argument(
        "-Inventory",
        "--inventory",
        type=Path,
        default=project_folder / "equipements.csv",
        help="Chemin du CSV (par défaut : equipements.csv à côté du script).",
    )
    parser.add_argument(
        "-BackupFolder",
        "--backup-folder",
        type=Path,
        default=project_folder / "sauvegardes",
        help="Dossier de sortie (par défaut : sauvegardes à côté du script).",
    )
    return parser.parse_args()


def main() -> int:
    """Run the backup and report inventory/setup errors."""
    arguments = parse_arguments()
    try:
        return run(arguments.inventory, arguments.backup_folder)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"[ERREUR] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
