import streamlit as st
import time
import threading
import queue
import pandas as pd
import traceback
from dotenv import load_dotenv
import pyupbit

from utils.common_utils import get_env
from upbit_api import UpbitAPI
from order_db import (
    init_order_db,
    save_order,
    get_recent_orders,
    get_pending_orders,
    update_order_status,
)

# ==============================================================================
# 상수 및 설정 (Constants & Configurations)
# ==============================================================================
REBALANCE_RATIO_OPTIONS = [5, 10, 15, 20]
REBALANCE_PRICE_OPTIONS = [3, 5, 10, 15, 20]
TERM_MIN, TERM_MAX, TERM_DEFAULT = 1, 24, 1


# ==============================================================================
# 애플리케이션 상태 관리 (Application State Management)
# ==============================================================================
class AppState:
    """Streamlit 세션 상태를 관리하는 클래스"""

    def __init__(self):
        defaults = {
            "tickers": [],
            "selected_ticker": None,
            "balance": 0,
            "current_price": 0,
            "log_queue": queue.Queue(),
            "rebalance_thread": None,
            "stop_event": threading.Event(),
            "orders": [],
            "orders_refresh_needed": True,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @property
    def tickers(self):
        return st.session_state.tickers

    @tickers.setter
    def tickers(self, value):
        st.session_state.tickers = value

    @property
    def selected_ticker(self):
        return st.session_state.selected_ticker

    @selected_ticker.setter
    def selected_ticker(self, value):
        st.session_state.selected_ticker = value

    @property
    def balance(self):
        return st.session_state.balance

    @balance.setter
    def balance(self, value):
        st.session_state.balance = value

    @property
    def current_price(self):
        return st.session_state.current_price

    @current_price.setter
    def current_price(self, value):
        st.session_state.current_price = value

    @property
    def log_queue(self) -> queue.Queue:
        return st.session_state.log_queue

    @property
    def rebalance_thread(self) -> threading.Thread:
        return st.session_state.rebalance_thread

    @rebalance_thread.setter
    def rebalance_thread(self, value: threading.Thread):
        st.session_state.rebalance_thread = value

    @property
    def stop_event(self) -> threading.Event:
        return st.session_state.stop_event

    @property
    def orders(self):
        return st.session_state.orders

    @orders.setter
    def orders(self, value):
        st.session_state.orders = value

    @property
    def orders_refresh_needed(self):
        return st.session_state.orders_refresh_needed

    @orders_refresh_needed.setter
    def orders_refresh_needed(self, value: bool):
        st.session_state.orders_refresh_needed = value

    def is_thread_alive(self):
        return bool(self.rebalance_thread and self.rebalance_thread.is_alive())

    def log(self, message):
        self.log_queue.put(message)


# ==============================================================================
# API 및 DB 초기화 (API & DB Initialization)
# ==============================================================================
@st.cache_resource
def get_upbit_api():
    """UpbitAPI 인스턴스를 생성하고 캐시합니다."""
    load_dotenv(verbose=True, dotenv_path="envs/.env", override=True)
    access_key = get_env("ACCESS_KEY")
    secret_key = get_env("SECRET_KEY")
    if not access_key or not secret_key:
        st.error("Upbit API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
        st.stop()
    return UpbitAPI(access_key, secret_key)


def initialize_app():
    """앱 처음 실행 시 필요한 DB 등을 초기화합니다."""
    init_order_db()


# ==============================================================================
# 비즈니스 로직 (Business Logic)
# ==============================================================================
def sync_all_pending_orders(api: UpbitAPI, state: AppState):
    """DB의 모든 미체결 주문 상태를 Upbit과 동기화합니다."""
    pending_orders = get_pending_orders()
    state.log(f"[주문 동기화] 미체결 주문 {len(pending_orders)}건 상태 확인 시작")
    changed = False
    for order in pending_orders:
        try:
            uuid = order[2]
            if not uuid or not isinstance(uuid, str):
                state.log(f"[경고] 유효하지 않은 UUID: {order}")
                continue

            status = api.check_order_status(uuid)
            state.log(f"[주문 상태 갱신] UUID: {uuid}, 상태: {status}")
            if status != order[5]:  # 상태가 변경된 경우
                update_order_status(uuid, status)
                changed = True
        except Exception as e:
            state.log(f"[오류] 주문 상태 동기화 실패: {e}, 주문: {order}")
            state.log(traceback.format_exc())
    return changed


def place_new_orders(api: UpbitAPI, state: AppState, ticker, ratio, price_ratio):
    """새로운 리밸런싱 매수/매도 주문을 제출합니다."""
    try:
        current_price = pyupbit.get_current_price(ticker)
        state.log(f"[{ticker}] 현재가: {current_price}")
        balance = api.get_balance(ticker)
        state.log(f"[{ticker}] 보유 수량: {balance}")

        amount = round(balance * ratio, 8)
        state.log(f"[{ticker}] 주문 수량: {amount}")

        order_info = api.rebalancing_orders(ticker, current_price, amount, price_ratio)

        if not (
            order_info and order_info.get("sell_uuid") and order_info.get("buy_uuid")
        ):
            state.log(
                "[오류] 주문 정보가 비어있거나 UUID가 없습니다. 주문 저장을 건너뜁니다."
            )
            state.log(f"[진단] 전체 주문 정보: {order_info}")
            state.log(
                f"[진단] 주문 수량: {amount}, 최소 주문 금액: {current_price * amount}"
            )
            return

        # 주문 정보 DB에 저장
        for side in ["sell", "buy"]:
            save_order(
                ticker=ticker,
                order_type=side,
                uuid=order_info[f"{side}_uuid"],
                price=float(order_info[f"{side}_price"]),
                amount=float(amount),
                status="requested",
            )
        state.log(f"[매도 주문] 가격: {order_info['sell_price']:.2f}, 수량: {amount}")
        state.log(f"[매수 주문] 가격: {order_info['buy_price']:.2f}, 수량: {amount}")

    except Exception as e:
        state.log(f"[오류] 신규 주문 발주 중 예외 발생: {e}")
        state.log(traceback.format_exc())


def rebalance_loop(
    api: UpbitAPI,
    log_queue: queue.Queue,
    stop_event: threading.Event,
    ticker,
    ratio,
    price_ratio,
    term_hour,
):
    """리밸런싱 로직을 주기적으로 실행하는 메인 루프 (Thread-safe 객체만 사용)"""
    log_queue.put("[리밸런싱 루프 시작]")
    while not stop_event.is_set():
        try:
            # 주문 동기화
            pending_orders = get_pending_orders()
            log_queue.put(
                f"[주문 동기화] 미체결 주문 {len(pending_orders)}건 상태 확인 시작"
            )
            for order in pending_orders:
                try:
                    uuid = order[2]
                    if not uuid or not isinstance(uuid, str):
                        log_queue.put(f"[경고] 유효하지 않은 UUID: {order}")
                        continue
                    status = api.check_order_status(uuid)
                    log_queue.put(f"[주문 상태 갱신] UUID: {uuid}, 상태: {status}")
                    if status != order[5]:
                        update_order_status(uuid, status)
                except Exception as e:
                    log_queue.put(f"[오류] 주문 상태 동기화 실패: {e}, 주문: {order}")
                    log_queue.put(traceback.format_exc())
            log_queue.put(f"[미체결 주문 확인] {len(pending_orders)}건")
            if not pending_orders:
                log_queue.put(
                    "[상태] 모든 주문 체결 완료. 신규 리밸런싱 주문을 시작합니다."
                )
                # 신규 주문 발주
                try:
                    current_price = pyupbit.get_current_price(ticker)
                    log_queue.put(f"[{ticker}] 현재가: {current_price}")
                    balance = api.get_balance(ticker)
                    log_queue.put(f"[{ticker}] 보유 수량: {balance}")
                    amount = round(balance * ratio, 8)
                    log_queue.put(f"[{ticker}] 주문 수량: {amount}")
                    order_info = api.rebalancing_orders(
                        ticker, current_price, amount, price_ratio
                    )
                    if not (
                        order_info
                        and order_info.get("sell_uuid")
                        and order_info.get("buy_uuid")
                    ):
                        log_queue.put(
                            "[오류] 주문 정보가 비어있거나 UUID가 없습니다. 주문 저장을 건너뜁니다."
                        )
                        log_queue.put(f"[진단] 전체 주문 정보: {order_info}")
                        log_queue.put(
                            f"[진단] 주문 수량: {amount}, 최소 주문 금액: {current_price * amount}"
                        )
                        continue
                    for side in ["sell", "buy"]:
                        save_order(
                            ticker=ticker,
                            order_type=side,
                            uuid=order_info[f"{side}_uuid"],
                            price=float(order_info[f"{side}_price"]),
                            amount=float(amount),
                            status="requested",
                        )
                    log_queue.put(
                        f"[매도 주문] 가격: {order_info['sell_price']:.2f}, 수량: {amount}"
                    )
                    log_queue.put(
                        f"[매수 주문] 가격: {order_info['buy_price']:.2f}, 수량: {amount}"
                    )
                except Exception as e:
                    log_queue.put(f"[오류] 신규 주문 발주 중 예외 발생: {e}")
                    log_queue.put(traceback.format_exc())
            else:
                log_queue.put(
                    f"[상태] 미체결 주문이 남아있어 대기합니다. ({len(pending_orders)}건)"
                )
            log_queue.put(f"[대기] {term_hour}시간 후 다음 확인을 시작합니다.")
            stop_event.wait(term_hour * 3600)
        except Exception as e:
            log_queue.put(f"[오류] 리밸런싱 루프 중 예외 발생: {e}")
            log_queue.put(traceback.format_exc())
            stop_event.wait(60)
    log_queue.put("[리밸런싱 루프 종료]")


# ==============================================================================
# Streamlit UI 렌더링 (Streamlit UI Rendering)
# ==============================================================================
def render_sidebar(api: UpbitAPI, state: AppState):
    """사이드바 UI 구성"""
    st.sidebar.title("⚙️ 리밸런싱 설정")

    # Ticker 선택
    if not state.tickers:
        state.tickers = api.get_tickers()
    state.selected_ticker = st.sidebar.selectbox(
        "코인 선택", state.tickers, key="ticker_select"
    )

    if state.selected_ticker:
        state.balance = api.get_balance(state.selected_ticker)
        state.current_price = pyupbit.get_current_price(state.selected_ticker)
        st.sidebar.metric("현재가", f"{state.current_price:,.0f} KRW")
        st.sidebar.metric(
            "보유수량",
            f"{state.balance:,.4f} {state.selected_ticker.replace('KRW-', '')}",
        )

    # 리밸런싱 설정
    ratio = st.sidebar.selectbox("리밸런싱 비율(%)", REBALANCE_RATIO_OPTIONS, index=0)
    price_ratio = st.sidebar.selectbox(
        "리밸런싱 가격(%)", REBALANCE_PRICE_OPTIONS, index=0
    )
    term_hour = st.sidebar.number_input(
        "주문 상태 확인 주기(시간)",
        min_value=TERM_MIN,
        max_value=TERM_MAX,
        value=TERM_DEFAULT,
    )
    return ratio / 100, price_ratio / 100, term_hour


def render_control_buttons(api: UpbitAPI, state: AppState, config):
    """START/STOP 버튼 UI 구성"""
    st.sidebar.write("---")
    ratio_val, price_ratio_val, term_hour = config
    rebalance_amount = state.balance * ratio_val if state.balance else 0
    buy_price = (
        state.current_price * (1 - price_ratio_val) if state.current_price else 0
    )
    min_krw_required = buy_price * rebalance_amount
    my_krw = api.get_krw_balance()
    st.sidebar.metric("내 KRW 잔액", f"{my_krw:,.0f} KRW")
    is_krw_insufficient = my_krw < min_krw_required
    if is_krw_insufficient:
        st.sidebar.warning(
            f"매수에 필요한 KRW가 부족합니다. (필요: {min_krw_required:,.0f} KRW)"
        )
    col1, col2 = st.sidebar.columns(2)
    start_disabled = is_krw_insufficient or state.is_thread_alive()
    if col1.button("START", disabled=start_disabled, use_container_width=True):
        state.stop_event.clear()
        thread = threading.Thread(
            target=rebalance_loop,
            args=(
                api,
                state.log_queue,
                state.stop_event,
                state.selected_ticker,
                ratio_val,
                price_ratio_val,
                term_hour,
            ),
            daemon=True,
        )
        state.rebalance_thread = thread
        thread.start()
        st.rerun()
    stop_disabled = not state.is_thread_alive()
    if col2.button("STOP", disabled=stop_disabled, use_container_width=True):
        state.stop_event.set()
        st.toast("자동 주문 중지를 요청했습니다. 현재 주기를 마치고 종료됩니다.")
        st.rerun()
    if state.is_thread_alive():
        st.sidebar.success("리밸런싱 봇이 실행 중입니다...")


def render_order_history(api: UpbitAPI, state: AppState):
    """주문 이력 UI 구성"""
    st.header("📋 주문 이력")
    if st.button("새로고침", key="refresh_orders_btn"):
        state.orders_refresh_needed = True
        sync_all_pending_orders(api, state)

    if state.orders_refresh_needed:
        state.orders = get_recent_orders(20)
        state.orders_refresh_needed = False

    if not state.orders:
        st.info("주문 이력이 없습니다.")
        return

    df = pd.DataFrame(
        state.orders,
        columns=["티커", "타입", "UUID", "가격", "수량", "상태", "생성시각"],
    )
    st.dataframe(df, hide_index=True, use_container_width=True)


def render_logs(state: AppState):
    """실시간 로그 UI 구성"""
    st.header("📜 실시간 로그")
    log_container = st.container(height=300)

    log_messages = []
    while not state.log_queue.empty():
        log_messages.append(state.log_queue.get())

    if log_messages:
        # Append new logs to a persistent log history in session state
        if "log_history" not in st.session_state:
            st.session_state.log_history = []
        st.session_state.log_history.extend(log_messages)

    # Display logs
    for msg in reversed(st.session_state.get("log_history", [])):
        log_container.text(msg)


def render_main_content(api: UpbitAPI, state: AppState):
    """메인 화면 UI 구성"""
    st.title("📈 Upbit 자동 리밸런싱 봇")
    st.markdown("---")

    render_order_history(api, state)
    st.markdown("---")
    render_logs(state)


# ==============================================================================
# 메인 실행 (Main Execution)
# ==============================================================================
def main():
    """Streamlit 애플리케이션의 메인 함수"""
    st.set_page_config(layout="wide", page_title="Upbit 리밸런싱 봇")

    initialize_app()
    api = get_upbit_api()
    state = AppState()

    # 최초 실행 시 주문 상태 동기화
    if "initial_sync_done" not in st.session_state:
        sync_all_pending_orders(api, state)
        st.session_state.initial_sync_done = True

    config = render_sidebar(api, state)
    render_control_buttons(api, state, config)
    render_main_content(api, state)

    # UI 자동 갱신을 위한 코드
    if state.is_thread_alive():
        time.sleep(5)
        st.rerun()


if __name__ == "__main__":
    main()
