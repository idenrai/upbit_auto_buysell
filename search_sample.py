import argparse
import boto3
from boto3.dynamodb.conditions import Key, Attr
import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from utils.common_utils import get_env, load_config
from utils.json_utils import save_to_json
from utils.validate_utils import validate_env_name


def setup_logger():
    """
    Logger
    :return:
    """
    # Create logger
    _logger = logging.getLogger("Logger")
    _logger.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Create file handler
    log_file = "./logs/search_sample_{}.log".format(timestamp)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)

    # Create console_handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    _logger.addHandler(console_handler)

    return _logger


def execute():
    """
    Execute
    :return:
    """
    # DynamoDB 설정
    dynamodb = boto3.resource('dynamodb', endpoint_url=get_env("DYNAMO_DB_ENDPOINT"))
    document_table = dynamodb.Table(get_env("DYNAMO_DB_DOCUMENT_TABLE"))

    # 중간 파일 폴더 작성
    intermediate_folder = os.path.join(
        conf["intermediate_base_folder"], timestamp
    )
    os.makedirs(intermediate_folder)
    target_db_file = os.path.join(intermediate_folder, conf["filename_prefix"] + "_db.json")

    # DynamoDB 로부터 데이터 취득
    target_date = (datetime.now() - timedelta(days=conf["days_ago"])).strftime('%Y-%m-%d')

    logger.info("Get target documents from DynamoDB")
    logger.info(f"Target : Documents created before {target_date}")
    response = document_table.scan(
        FilterExpression=Key('created_at').lt(target_date) & Attr('status').eq('INSERTED')
    )
    target_documents = response['Items']

    while 'LastEvaluatedKey' in response:
        response = document_table.scan(
            FilterExpression=Key('created_at').lt(target_date) & Attr('status').eq('INSERTED'),
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        target_documents.extend(response['Items'])

    save_to_json(target_db_file, target_documents)

    logger.info(f"DB file path: {target_db_file}")
    logger.info(f"Target documents : {len(target_documents)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env", type=validate_env_name, required=True, help="Environment to be updated"
    )
    args = parser.parse_args()
    env = args.env.lower()

    # 환경변수 로드
    load_dotenv(verbose=True)
    load_dotenv(f"envs/.{env}.env", override=True)

    # Config
    conf = load_config()

    # 글로벌 변수로 Logger 를 만들어 두기
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    timestamp = now.strftime("%Y%m%d%H%M%S")
    logger = setup_logger()
    logger.info(f"Processing {env} environment")

    execute()
