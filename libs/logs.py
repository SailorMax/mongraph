import json


def log_error(msg):
    print(f"(!) {msg}")


def pre(obj):
    print(json.dumps(obj))
