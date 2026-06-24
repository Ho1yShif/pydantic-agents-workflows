"""Render Workflows service for the Ask Render Anything Assistant.

Hosts the Q&A pipeline orchestrator + parallel ingestion fan-out tasks. Task
logic reuses the existing ``backend.pipeline`` functions and ``data.scripts``
ingestion scripts unchanged; this package only adds thin task wrappers and the
JSON (de)serialization that task boundaries require.
"""
