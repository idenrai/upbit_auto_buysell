import pyupbit
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


# Upbit API 관련 함수
class UpbitAPI:
    def __init__(self, access_key, secret_key):
        self.upbit = pyupbit.Upbit(access_key, secret_key)

    def get_krw_balance(self):
        balances = self.upbit.get_balances()
        for balance in balances:
            if balance["currency"] == "KRW":
                return float(balance["balance"])
        return 0

    def get_balance(self, ticker):
        balances = self.upbit.get_balances()
        for balance in balances:
            if balance["currency"] == ticker.split("-")[1]:
                return float(balance["balance"])
        return 0

    def get_tickers(self):
        balances = self.upbit.get_balances()
        tickers = []
        for balance in balances:
            if balance["currency"] != "KRW":
                ticker = f"KRW-{balance['currency']}"
                tickers.append(ticker)
        return tickers

    def check_order_status(self, ticker):
        orders = self.upbit.get_order(ticker)
        logger.info(f"Orders: {orders}")
        if not orders:
            return True
        for order in orders:
            if order["status"] != "done":
                return False
        return True

    def rebalancing_orders(self, ticker, price, amount):
        sell_price = price * 1.2
        logger.info(f"[{ticker}] Sell price: {sell_price}, Sell amount: {amount:.8f}")
        # sell_order = self.upbit.sell_limit_order(ticker, sell_price, amount)
        # logger.info(f"[{ticker}] Sell order placed: {sell_order}")

        buy_price = price * 0.8
        logger.info(f"[{ticker}] Buy price: {buy_price}, Buy amount: {amount:.8f}")
        # buy_order = self.upbit.buy_limit_order(ticker, buy_price, amount)
        # logger.info(f"[{ticker}]Buy order placed: {buy_order}")


def execute():
    """
    Execute
    :return:
    """

    krw_balance = upbit_api.get_krw_balance()
    logger.info(f"KRW Balance: {krw_balance}")

    tickers = upbit_api.get_tickers()
    logger.info(f"Tickers: {tickers}")

    # 티커별 잔고 조회
    for ticker in tickers:
        balance = upbit_api.get_balance(ticker)
        logger.info(f"Balance for {ticker}: {balance}")
        current_price = pyupbit.get_current_price(ticker)
        logger.info(f"Current price for {ticker}: {current_price}")

        if upbit_api.check_order_status(ticker):
            amount = round(10000 / current_price, 8)
            upbit_api.rebalancing_orders(ticker, current_price, amount)
            logger.info(f"Rebalancing orders placed for {ticker}")


if __name__ == "__main__":
    # 환경변수 로드
    load_dotenv(verbose=True)
    load_dotenv("envs/.env", override=True)

    # Config
    conf = load_config()

    # 글로벌 변수로 Logger 를 만들어 두기
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    timestamp = now.strftime("%Y%m%d%H%M%S")
    logger = setup_logger()

    access_key = get_env("ACCESS_KEY")
    secret_key = get_env("SECRET_KEY")

    try:
        upbit_api = UpbitAPI(access_key, secret_key)
        logger.info("Upbit API initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing Upbit API: {e}")
        exit(1)

    execute()
