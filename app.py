import streamlit as st
import time
import threading
from dotenv import load_dotenv
import pyupbit
import queue
import pandas as pd
from utils.common_utils import get_env
from upbit_api import UpbitAPI
from order_db import (
    init_order_db,
    save_order,
    get_recent_orders,
    get_pending_orders,
    update_order_status,
)
import traceback

# ====== 상수 및 옵션 ======
REBALANCE_RATIO_OPTIONS = [5, 10, 15, 20]
REBALANCE_PRICE_OPTIONS = [3, 5, 10, 15, 20]
TERM_MIN, TERM_MAX, TERM_DEFAULT = 1, 24, 1


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


def log_callback_factory(log_queue):
    def log_callback(msg):
        log_queue.put(msg)

    return log_callback


def update_all_pending_orders_status(api):
    """
    DB의 미체결 주문 상태를 Upbit에서 확인하여 DB에 반영한다.
    상태가 변경된 주문이 있으면 True, 아니면 False 반환.
    """
    pending_orders = get_pending_orders()
    print(f"[주문 상태 갱신] 미체결 주문 {len(pending_orders)}건 상태 동기화 시작")
    changed = False
    for order in pending_orders:
        try:
            uuid = order[2]
            if not uuid:
                print(f"[경고] uuid 없음: {order}")
                continue
            if not isinstance(uuid, str):
                uuid = str(uuid)
            status = api.check_order_status(uuid)
            print(f"[주문 상태 갱신] uuid={uuid}, status={status}")
            if status in ("done", "cancel", "wait", "watch", "unknown"):
                update_order_status(uuid, status)
                changed = True
        except Exception as e:
            print(f"[ERROR] 주문 상태 동기화 실패: {e}, order={order}")
            print(traceback.format_exc())
    return changed


def process_pending_orders(api, update_order_status_func, term_hour, stop_flag):
    """
    미체결 주문 상태 확인 및 갱신 공통 처리 함수.
    모든 주문이 done/cancel이면 True, 아니면 False 반환.
    """
    update_all_pending_orders_status(api)
    pending_orders = get_pending_orders()
    print(f"[미체결 주문 개수] {len(pending_orders)}건")
    if not pending_orders:
        print("[모든 주문 체결] 미체결 주문 없음. 리밸런싱 주문을 시작합니다.")
        return True
    print(f"[미체결 주문 감지] {len(pending_orders)}건. 상태 확인 및 갱신 중...")
    if not stop_flag[0]:
        print(f"[Watching] 미체결 주문이 남아 있습니다. {term_hour}시간 후 재확인.")
        time.sleep(term_hour * 3600)
    return False


# ====== 리밸런싱 반복 실행 ======
def rebalance_loop(api, ticker, ratio, price_ratio, term_hour, log_callback, stop_flag):
    print("[리밸런싱 루프 시작]")
    while not stop_flag[0]:
        try:
            # 1. 미체결 주문 처리 (공통 함수 사용)
            if not process_pending_orders(
                api, update_order_status, term_hour, stop_flag
            ):
                continue
        except Exception as e:
            print(f"[ERROR] 미체결 주문 확인/처리 중 예외 발생: {e}")
            print(traceback.format_exc())
            time.sleep(10)
            continue
        # 2. 새 주문 발주 (오직 미체결 주문이 없을 때만!)
        print(f"[주문 준비] ticker={ticker}, ratio={ratio}, price_ratio={price_ratio}")
        try:
            current_price = pyupbit.get_current_price(ticker)
            print(f"[현재가 조회] {ticker}: {current_price}")
            balance = api.get_balance(ticker)
            print(f"[잔고 조회] {ticker}: {balance}")
            amount = round(balance * ratio, 8)
            print(f"[주문 수량 계산] {amount}")

            order_info = api.rebalancing_orders(
                ticker, current_price, amount, price_ratio
            )
            print(f"[DEBUG] order_info: {order_info}")
            if (
                not order_info
                or not order_info.get("sell_uuid")
                or not order_info.get("buy_uuid")
            ):
                print(
                    "[ERROR] 주문 정보가 비어있거나 uuid가 없습니다. 주문 저장을 건너뜁니다."
                )
                # 추가 진단: 최소 주문 수량/금액, API 응답, order_info 전체 출력
                print(f"[진단] order_info 전체: {order_info}")
                print(
                    f"[진단] 주문 수량: {amount}, 최소 주문 금액 조건: {current_price * amount}"
                )
                print(f"[진단] API 응답: {getattr(api, 'last_response', None)}")
                time.sleep(10)
                continue
            save_order(
                ticker,
                "sell",
                order_info["sell_uuid"],
                (
                    float(order_info["sell_price"])
                    if order_info["sell_price"] is not None
                    else 0.0
                ),
                float(amount) if amount is not None else 0.0,
                "requested",
            )
            save_order(
                ticker,
                "buy",
                order_info["buy_uuid"],
                (
                    float(order_info["buy_price"])
                    if order_info["buy_price"] is not None
                    else 0.0
                ),
                float(amount) if amount is not None else 0.0,
                "requested",
            )
            print(
                f"[매도 주문] 가격: {order_info['sell_price']:.2f} / 수량: {amount} / uuid: {order_info['sell_uuid']}"
            )
            print(
                f"[매수 주문] 가격: {order_info['buy_price']:.2f} / 수량: {amount} / uuid: {order_info['buy_uuid']}"
            )
        except Exception as e:
            print(f"[ERROR] 주문 발주 중 예외 발생: {e}")
            print(traceback.format_exc())
            time.sleep(10)
            continue
        # 주문 Watch 루프 (최초 주문 후)
        while not stop_flag[0]:
            if process_pending_orders(api, update_order_status, term_hour, stop_flag):
                print(
                    "[Watching] 모든 주문이 체결되었습니다. 다음 리밸런싱을 준비합니다."
                )
                break
    print("[리밸런싱 루프 종료]")


# ====== Streamlit UI ======
st.title("Upbit 자동 리밸런싱 주문")
init_session_state()
api = get_upbit_api()
global_log_queue = queue.Queue()
log_callback = log_callback_factory(global_log_queue)
init_order_db()

if not st.session_state["tickers"]:
    st.session_state["tickers"] = api.get_tickers()
    st.session_state["selected_ticker"] = None

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

ratio = st.selectbox("리밸런싱 비율(%)", REBALANCE_RATIO_OPTIONS, index=0)
ratio_val = ratio / 100
rebalance_amount = (
    st.session_state["balance"] * ratio_val if st.session_state["balance"] else 0
)
st.write(f"리밸런싱 수량: {rebalance_amount}")

price_ratio = st.selectbox("리밸런싱 가격(%)", REBALANCE_PRICE_OPTIONS, index=0)
price_ratio_val = price_ratio / 100
if st.session_state["current_price"]:
    sell_price = int(round(st.session_state["current_price"] * (1 + price_ratio_val)))
    buy_price = int(round(st.session_state["current_price"] * (1 - price_ratio_val)))
    st.write(f"매도가: {sell_price}")
    st.write(f"매수가: {buy_price}")
    min_krw_required = buy_price * rebalance_amount
    st.write(f"매수 주문 체결 시 필요한 최소 KRW: {min_krw_required:.2f}")
    my_krw = api.get_krw_balance()
    st.write(f"내 KRW 잔액: {my_krw:.2f}")
    krw_warning = my_krw < min_krw_required
    if krw_warning:
        st.warning(
            "KRW 잔액이 부족합니다. 매수 주문 체결 시 필요한 최소 KRW보다 적습니다."
        )
else:
    krw_warning = False

term_hour = st.number_input(
    "주문 상태 확인 Term(시간)",
    min_value=TERM_MIN,
    max_value=TERM_MAX,
    value=TERM_DEFAULT,
)

# 버튼 영역: START/STOP 버튼을 한 줄에 붙여서 배치
col1, col2, _ = st.columns([1, 1, 6])
with col1:
    start_disabled = krw_warning or (
        st.session_state["thread"] is not None and st.session_state["thread"].is_alive()
    )
    if st.button("START", disabled=start_disabled):
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
    stop_disabled = not (
        st.session_state["thread"] is not None and st.session_state["thread"].is_alive()
    )
    if st.button("STOP", disabled=stop_disabled):
        st.session_state["stop_flag"][0] = True
        st.write("자동 주문 중지 요청됨.")

st.write("---")
while not global_log_queue.empty():
    msg = global_log_queue.get()
    st.session_state["log"].append(msg)
for msg in st.session_state["log"]:
    st.write(msg)


# ====== 주문 상태 동기화 및 이력 조회 ======
def sync_pending_orders_and_get_history(api, limit=20):
    """
    1. DB에서 미체결 주문을 upbit에서 동기화
    2. 최신 주문 이력 반환
    """
    try:
        update_all_pending_orders_status(api)
        orders = get_recent_orders(limit)
        return orders
    except Exception as e:
        print(f"[ERROR] 주문 동기화 전체 실패: {e}")
        print(traceback.format_exc())
        return []


def render_recent_orders_ui(api):
    """
    주문 이력 및 새로고침 UI 렌더링
    """
    st.write("## 최근 주문 이력 (최신 20건)")
    if st.button("주문 이력 새로고침", key="refresh_orders_btn"):
        st.session_state["orders_refresh"] = True
    # 버튼 클릭 또는 최초 진입 시만 갱신
    if st.session_state.get("orders_refresh", True):
        orders = sync_pending_orders_and_get_history(api)
        st.session_state["orders"] = orders
        st.session_state["orders_refresh"] = False
    else:
        orders = st.session_state.get("orders", [])
    if not orders:
        st.write("주문 이력이 없습니다.")
        return
    columns = ["티커", "타입", "UUID", "가격", "수량", "상태", "생성시각"]
    n_cols = len(orders[0])
    use_columns = columns[:n_cols]
    if n_cols != len(columns):
        st.write(f"[DEBUG] orders[0]: {orders[0]}")
        st.write(f"[DEBUG] row 컬럼 개수: {n_cols}, columns: {use_columns}")
    df = pd.DataFrame(orders, columns=use_columns)
    st.dataframe(df, hide_index=True)


render_recent_orders_ui(api)
