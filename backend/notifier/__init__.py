"""Incident Notifier — polling-based alerting for LCC monitoring API.

Integrated into the lcc-tools FastAPI backend. The poller fetches
open incidents, the service handles escalation and alert routing,
and the api module exposes a REST API for the Svelte frontend.
"""
