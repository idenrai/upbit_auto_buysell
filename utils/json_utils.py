import json
from decimal import Decimal
from types import GeneratorType


def custom_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, GeneratorType):
        return list(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def save_to_json(file_path, data):
    with open(file_path, 'w') as json_file:
        json.dump(data, json_file, default=custom_default)


def load_from_json(file_path):
    with open(file_path, 'r') as json_file:
        return json.load(json_file)
