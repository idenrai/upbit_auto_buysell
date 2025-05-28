import pyupbit


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
        currency = ticker.split("-")[1]
        balances = self.upbit.get_balances()
        for balance in balances:
            if balance["currency"] == currency:
                return float(balance["balance"])
        return 0

    def get_tickers(self):
        balances = self.upbit.get_balances()
        return [f"KRW-{b['currency']}" for b in balances if b["currency"] != "KRW"]

    def rebalancing_orders(self, ticker, price, amount, ratio):
        # KRW 마켓은 주문 가격이 반드시 정수여야 함
        sell_price = int(round(price * (1 + ratio)))
        buy_price = int(round(price * (1 - ratio)))
        sell_order = self.upbit.sell_limit_order(ticker, sell_price, amount)
        print(f"[DEBUG] sell_order 응답: {sell_order}")
        buy_order = self.upbit.buy_limit_order(ticker, buy_price, amount)
        print(f"[DEBUG] buy_order 응답: {buy_order}")
        sell_uuid = sell_order.get("uuid") if isinstance(sell_order, dict) else None
        buy_uuid = buy_order.get("uuid") if isinstance(buy_order, dict) else None
        return {
            "sell_price": sell_price,
            "buy_price": buy_price,
            "sell_uuid": sell_uuid,
            "buy_uuid": buy_uuid,
            "sell_order_raw": sell_order,
            "buy_order_raw": buy_order,
        }

    def check_order_status(self, uuid):
        if not uuid:
            print("[DEBUG] check_order_status: uuid is None or empty, return 'unknown'")
            return "unknown"
        order = self.upbit.get_order(uuid)
        print(f"[DEBUG] check_order_status: get_order({uuid}) => {order}")
        if isinstance(order, dict):
            status = order.get("state", "unknown")
            print(f"[DEBUG] check_order_status: status={status}")
            return status
        print("[DEBUG] check_order_status: order is not dict, return 'unknown'")
        return "unknown"
