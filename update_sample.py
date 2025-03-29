import argparse
import boto3
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from tqdm import tqdm

from dotenv import load_dotenv

from utils.common_utils import get_env, load_config
from utils.json_utils import load_from_json
from utils.validate_utils import validate_env_name, validate_datetime


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
    log_file = "./logs/update_sample_{}.log".format(timestamp)
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
    実行関数
    :return:
    """
    # DynamoDB 설정
    dynamodb = boto3.resource('dynamodb', endpoint_url=get_env("DYNAMO_DB_ENDPOINT"))
    document_table = dynamodb.Table(get_env("DYNAMO_DB_DOCUMENT_TABLE"))

    # 중간 파일 취득
    intermediate_folder = os.path.join(
        conf["intermediate_base_folder"], folder_timestamp
    )
    target_db_file = os.path.join(intermediate_folder, conf["filename_prefix"] + "_db.json")
    target_db_data = load_from_json(target_db_file)

    # DynamoDB の Document 테이블에서 데이터 논리삭제
    # 해당되는 데이터의 `status`를 `DELETED`로 변경
    logger.info("Delete target documents from DynamoDB")
    for target_document in tqdm(target_db_data):
        update_response = document_table.update_item(
            Key={
                'id': target_document['id']
            },
            UpdateExpression='SET #status = :new_status',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':new_status': 'DELETED'
            }
        )
        logger.info(f"Updated document ID {id}: {update_response}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env", type=validate_env_name, required=True, help="Environment to be updated"
    )
    parser.add_argument(
        "--timestamp",
        type=validate_datetime,
        required=True,
        help="Timestamp in the format of YYYYMMDDHHMMSS",
    )
    args = parser.parse_args()
    env = args.env.lower()
    folder_timestamp = args.timestamp

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
