import os
from typing import Any
import yaml


def get_env(key: str, default_value: str = "") -> str:
    value = os.getenv(key, default_value)
    return value


def load_config(conf_file: str = "config.yaml") -> Any:
    with open(conf_file, "r") as file:
        config = yaml.safe_load(file)
    return config
