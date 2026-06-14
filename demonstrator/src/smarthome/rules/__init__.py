"""Automation rules — drop-in plugins (A-14).

Any module in this package that defines a ``Rule`` subclass is auto-discovered
and loaded by the controller. Adding behaviour therefore needs **no change to the
controller core** — just add a new file here.
"""
