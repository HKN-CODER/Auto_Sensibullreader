import sys
import os
import csv
import requests
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QGridLayout, QTableWidget, QTableWidgetItem
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont

URL = "https://oxide.sensibull.com/v1/compute/compute_intraday"

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_FILE = os.path.join(BASE_PATH, "sensibull_intraday.csv")
LOG_FILE = os.path.join(BASE_PATH, "sensibull_intraday_log.csv")


# ---------------------------
# 🔐 COOKIE (fallback method)
# ---------------------------
def load_cookie():
    cookie_path = os.path.join(BASE_PATH, "cookie.txt")

    if not os.path.exists(cookie_path):
        raise Exception("cookie.txt missing")

    with open(cookie_path, "r") as f:
        return f.read().strip()


# ---------------------------
# 📡 FETCH + FLATTEN ALL DATA
# ---------------------------
def fetch_data(cookie):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": "https://web.sensibull.com",
        "Referer": "https://web.sensibull.com/",
        "Cookie": cookie
    }

    res = requests.post(URL, headers=headers, json={"underlying": "NIFTY"}, timeout=10)

    if res.status_code in [401, 403]:
        raise Exception("COOKIE_EXPIRED")

    if res.status_code != 200:
        raise Exception(f"HTTP {res.status_code}")

    full = res.json()
    payload = full.get("payload", {})
    chart_data = payload.get("chart_data", {})

    if not chart_data:
        raise Exception("No chart_data")

    latest_time = sorted(chart_data.keys())[-1]
    d = chart_data[latest_time]

    row = {
        "time": latest_time,
        "spot": d.get("spot"),
        "future_price": d.get("price", {}).get("future"),
        "call_oi": d.get("oi_options", {}).get("call_oi"),
        "put_oi": d.get("oi_options", {}).get("put_oi"),
        "call_oi_change": d.get("oi_change_options", {}).get("call_oi_change"),
        "put_oi_change": d.get("oi_change_options", {}).get("put_oi_change"),
        "pcr": d.get("pcr_data", {}).get("pcr"),
        "max_pain": d.get("max_pain_data", {}).get("max_pain"),
        "atm_iv": d.get("iv", {}).get("atm_iv"),
        "atm_iv_change": d.get("iv", {}).get("atm_iv_change"),
        "atm_strike": d.get("iv", {}).get("atm_strike"),
        "vix": d.get("indiavix", {}).get("indiavix_price"),
        "ivp": d.get("ivp", {}).get("ivp"),
        "futures_oi": d.get("oi_futures", {}).get("futures_oi"),
        "strategy_pnl": d.get("strategy", {}).get("cumulative"),
    }

    # dynamic multi strategy
    ms = d.get("multi_strategy", {})
    for k, v in ms.items():
        row[f"ms_{k}_ltp"] = v.get("ltp")
        row[f"ms_{k}_change"] = v.get("ltp_change")

    return row


# ---------------------------
# 💾 SAVE
# ---------------------------
def save_snapshot(row):
    with open(SNAPSHOT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)


def append_log(row):
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ---------------------------
# 🖥️ GUI TABLE
# ---------------------------
class App(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Sensibull Dashboard")
        self.resize(300, 500)

        main_layout = QVBoxLayout()

        # 🔹 TOP METRICS
        self.grid = QGridLayout()

        self.lbl_pcr = QLabel("PCR: -")
        self.lbl_maxpain = QLabel("Max Pain: -")
        self.lbl_iv = QLabel("ATM IV: -")
        self.lbl_vix = QLabel("VIX: -")
        self.lbl_spot = QLabel("Spot: -")

        for lbl in [self.lbl_pcr, self.lbl_maxpain, self.lbl_iv, self.lbl_vix, self.lbl_spot]:
            lbl.setFont(QFont("Arial", 14, QFont.Bold))
            self.grid.addWidget(lbl)

        main_layout.addLayout(self.grid)

        # 🔹 TABLE (clean grouped view)
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Metric", "Value"])

        main_layout.addWidget(self.table)

        self.setLayout(main_layout)

        # 🔁 TIMER
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(1000)

    def update_data(self):
        try:
            cookie = load_cookie()
            data = fetch_data(cookie)

            # 🔥 TOP VALUES
            self.lbl_pcr.setText(f"PCR: {data.get('pcr')}")
            self.lbl_maxpain.setText(f"Max Pain: {data.get('max_pain')}")
            self.lbl_iv.setText(f"ATM IV: {data.get('atm_iv')}")
            self.lbl_vix.setText(f"VIX: {data.get('vix')}")
            self.lbl_spot.setText(f"Spot: {data.get('spot')}")

            # 🔥 COLOR LOGIC
            pcr = data.get("pcr") or 0
            if pcr > 1:
                self.lbl_pcr.setStyleSheet("color: green;")
            else:
                self.lbl_pcr.setStyleSheet("color: red;")

            # 🔹 TABLE CLEAN LIST
            display = {
                "Call OI": data.get("call_oi"),
                "Put OI": data.get("put_oi"),
                "Call OI Change": data.get("call_oi_change"),
                "Put OI Change": data.get("put_oi_change"),
                "Future Price": data.get("future_price"),
                "ATM Strike": data.get("atm_strike"),
                "IVP": data.get("ivp"),
                "Futures OI": data.get("futures_oi"),
                "Strategy PnL": data.get("strategy_pnl"),
            }

            self.table.setRowCount(len(display))

            for i, (k, v) in enumerate(display.items()):
                self.table.setItem(i, 0, QTableWidgetItem(k))
                self.table.setItem(i, 1, QTableWidgetItem(str(v)))

            save_snapshot(data)
            append_log(data)

        except Exception as e:
            self.lbl_pcr.setText(f"Error: {str(e)}")

# ---------------------------
# 🚀 MAIN
# ---------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())