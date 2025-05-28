import duckdb


def init_order_db():
    con = duckdb.connect("orders.duckdb")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            ticker VARCHAR,
            order_type VARCHAR,
            uuid VARCHAR,
            price DOUBLE,
            amount DOUBLE,
            status VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.close()


def save_order(ticker, order_type, uuid, price, amount, status):
    con = duckdb.connect("orders.duckdb")
    con.execute(
        "INSERT INTO orders (ticker, order_type, uuid, price, amount, status) VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, order_type, uuid, price, amount, status),
    )
    con.close()


def get_recent_orders(limit=20):
    con = duckdb.connect("orders.duckdb")
    result = con.execute(
        "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    return result


def get_pending_orders():
    con = duckdb.connect("orders.duckdb")
    result = con.execute(
        "SELECT * FROM orders WHERE status NOT IN ('done', 'cancel') ORDER BY created_at ASC"
    ).fetchall()
    con.close()
    return result


def update_order_status(uuid, status):
    con = duckdb.connect("orders.duckdb")
    con.execute(
        "UPDATE orders SET status=? WHERE uuid=?",
        (status, uuid),
    )
    con.close()
