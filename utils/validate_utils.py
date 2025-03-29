import argparse
from datetime import datetime


def validate_env_name(env_name: str):
    if env_name.lower() not in ["dev", "stg", "prd"]:
        raise argparse.ArgumentTypeError("Given env name not valid.")
    else:
        return env_name.lower()


def validate_datetime(datetime_string: str):
    try:
        datetime.strptime(datetime_string, "%Y%m%d%H%M%S")
        return datetime_string
    except ValueError:
        msg = "Given DateTime ({0}) not valid. Expected format: YYYYMMDDHHMMSS".format(datetime_string)
        raise argparse.ArgumentTypeError(msg)
