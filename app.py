import streamlit as st
import time
import threading
from dotenv import load_dotenv
import pyupbit

from utils.common_utils import get_env


# ====== 상수 및 옵션 ======
REBALANCE_RATIO_OPTIONS = [5, 10, 15, 20]
REBALANCE_PRICE_OPTIONS = [5, 10, 15, 20]
TERM_MIN, TERM_MAX, TERM_DEFAULT = 1, 24, 3


# ====== Upbit API Wrapper ======
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
        return [f"KRW-{b['currency']}" for b in balances if b["currency"] != "KRW"]

    def check_order_status(self, ticker):
        orders = self.upbit.get_order(ticker)
        if not orders:
            return True
        return all(order["status"] == "done" for order in orders)

    def rebalancing_orders(self, ticker, price, amount, ratio):
        sell_price = price * (1 + ratio)
        buy_price = price * (1 - ratio)
        # 실제 주문은 아래 주석 해제 필요
        # sell_order = self.upbit.sell_limit_order(ticker, sell_price, amount)
        # buy_order = self.upbit.buy_limit_order(ticker, buy_price, amount)
        return sell_price, buy_price


# ====== 환경변수 및 API 인스턴스 ======
def get_upbit_api():
    load_dotenv(verbose=True)
    load_dotenv("envs/.env", override=True)
    access_key = get_env("ACCESS_KEY")
    secret_key = get_env("SECRET_KEY")
    if not access_key or not secret_key:
        st.error(
            "ACCESS_KEY 또는 SECRET_KEY 환경변수가 없습니다. .env 파일 또는 환경설정을 확인하세요."
        )
        st.stop()
    return UpbitAPI(access_key, secret_key)


# ====== 세션 상태 관리 ======
def init_session_state():
    defaults = {
        "tickers": [],
        "selected_ticker": None,
        "balance": 0,
        "current_price": 0,
        "log": [],
        "thread": None,
        "stop_flag": [False],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def log_callback(msg):
    st.session_state["log"].append(msg)
    st.write(msg)


# ====== 리밸런싱 반복 실행 ======
def rebalance_loop(api, ticker, ratio, price_ratio, term_hour, log_callback, stop_flag):
    while not stop_flag[0]:
        current_price = pyupbit.get_current_price(ticker)
        balance = api.get_balance(ticker)
        amount = round(balance * ratio, 8)
        sell_price, buy_price = api.rebalancing_orders(
            ticker, current_price, amount, price_ratio
        )
        log_callback(f"매도 주문: {sell_price:.2f} / 수량: {amount}")
        log_callback(f"매수 주문: {buy_price:.2f} / 수량: {amount}")
        # 주문 상태 확인
        while not stop_flag[0]:
            if api.check_order_status(ticker):
                log_callback("주문 완료. 다음 리밸런싱 진행.")
                break
            log_callback(f"주문 미완료. {term_hour}시간 후 재확인.")
            time.sleep(term_hour * 3600)


# ====== Streamlit UI ======
st.title("Upbit 자동 리밸런싱 주문")
init_session_state()
api = get_upbit_api()

# 1. 보유 Ticker 자동 조회 및 선택
if not st.session_state["tickers"]:
    st.session_state["tickers"] = api.get_tickers()
    st.session_state["selected_ticker"] = None

# 2. Ticker 선택 및 정보 표시
if st.session_state["tickers"]:
    ticker = st.selectbox(
        "Ticker 선택", st.session_state["tickers"], key="ticker_select"
    )
    st.session_state["selected_ticker"] = ticker
    if ticker:
        st.session_state["balance"] = api.get_balance(ticker)
        st.session_state["current_price"] = pyupbit.get_current_price(ticker)
        st.write(f"현재가: {st.session_state['current_price']}")
        st.write(f"보유수량: {st.session_state['balance']}")

# 3. 리밸런싱 옵션 선택 및 계산
ratio = st.selectbox("리밸런싱 비율(%)", REBALANCE_RATIO_OPTIONS, index=0)
ratio_val = ratio / 100
rebalance_amount = (
    st.session_state["balance"] * ratio_val if st.session_state["balance"] else 0
)
st.write(f"리밸런싱 수량: {rebalance_amount}")

price_ratio = st.selectbox("리밸런싱 가격(%)", REBALANCE_PRICE_OPTIONS, index=0)
price_ratio_val = price_ratio / 100
if st.session_state["current_price"]:
    sell_price = st.session_state["current_price"] * (1 + price_ratio_val)
    buy_price = st.session_state["current_price"] * (1 - price_ratio_val)
    st.write(f"매도가: {sell_price:.2f}")
    st.write(f"매수가: {buy_price:.2f}")
    # 주문에 필요한 최소 KRW 계산 (매수 주문이 먼저 체결될 경우)
    min_krw_required = buy_price * rebalance_amount
    st.write(f"매수 주문 체결 시 필요한 최소 KRW: {min_krw_required:.2f}")
    # 내 KRW 잔액 확인 및 경고
    my_krw = api.get_krw_balance()
    st.write(f"내 KRW 잔액: {my_krw:.2f}")
    krw_warning = False
    if my_krw < min_krw_required:
        st.warning(
            "KRW 잔액이 부족합니다. 매수 주문 체결 시 필요한 최소 KRW보다 적습니다."
        )
        krw_warning = True
else:
    krw_warning = False

term_hour = st.number_input(
    "주문 상태 확인 Term(시간)",
    min_value=TERM_MIN,
    max_value=TERM_MAX,
    value=TERM_DEFAULT,
)

# 4. START/STOP 버튼
col1, col2 = st.columns(2)
with col1:
    if st.button("START", disabled=krw_warning):
        st.session_state["stop_flag"][0] = False
        if (
            st.session_state["thread"] is None
            or not st.session_state["thread"].is_alive()
        ):
            st.session_state["log"] = []
            st.session_state["thread"] = threading.Thread(
                target=rebalance_loop,
                args=(
                    api,
                    st.session_state["selected_ticker"],
                    ratio_val,
                    price_ratio_val,
                    term_hour,
                    log_callback,
                    st.session_state["stop_flag"],
                ),
                daemon=True,
            )
            st.session_state["thread"].start()
with col2:
    if st.button("STOP"):
        st.session_state["stop_flag"][0] = True
        st.write("자동 주문 중지 요청됨.")

# 5. 로그 출력
st.write("---")
for msg in st.session_state["log"]:
    st.write(msg)
