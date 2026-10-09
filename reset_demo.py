"""Rebuild the demo data around the current time. Stop the server first, then: python reset_demo.py"""
from app.main import rebuild_demo

rebuild_demo()
print("Demo data rebuilt.")
