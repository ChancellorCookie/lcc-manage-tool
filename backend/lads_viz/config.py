"""Zentrale Konfiguration — lädt backend/.env und exponiert Settings."""
import os
from pathlib import Path

from dotenv import load_dotenv

# backend/.env liegt ein Verzeichnis über app/
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OPC_URL = os.getenv("OPC_URL", "opc.tcp://10.89.11.52:4840")

DB_PATH = os.getenv(
    "DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "lads_viz.db"),
)
