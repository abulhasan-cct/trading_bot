import http.client
import json
import time
import requests
import logging
import streamlit as st
import numpy as np
import ta
import pandas as pd
from datetime import datetime, timedelta, timezone

# 📌 CONFIGURATION (API KEYS & SETTINGS)
API_KEY = "6kF02pNz5ERlkKG5"
API_EMAIL = "abuaseem119@gmail.com"
API_PASSWORD = "Password@786"
TELEGRAM_BOT_TOKEN = "7340249741:AAG6nI7bM0Pnwt29AzBXisiRQpRSOExQML0"
CHAT_ID = "1032676639"
BASE_URL = "demo-api-capital.backend-capital.com"  # Corrected URL
TRADE_AMOUNT = 1  # Trade size
RISK_PERCENTAGE = 1  # Stop-loss percentage
TP_MULTIPLIER = 3  # Take-profit multiplier
ASSET = "AAPL"  # Single asset to trade

# Global variables for authentication
security_token, cst_token = None, None

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# 📌 TELEGRAM NOTIFICATIONS
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            logging.info(f"📩 Telegram message sent: {message}")
        else:
            logging.error(f"⚠️ Failed to send Telegram message: {response.status_code}")
    except Exception as e:
        logging.error(f"⚠️ Error while sending Telegram message: {e}")


# 📌 AUTHENTICATION FUNCTION
def authenticate():
    global security_token, cst_token
    conn = http.client.HTTPSConnection(BASE_URL)
    payload = json.dumps({"identifier": API_EMAIL, "password": API_PASSWORD})
    headers = {"X-CAP-API-KEY": API_KEY, "Content-Type": "application/json"}

    conn.request("POST", "/api/v1/session", payload, headers)
    res = conn.getresponse()
    data = json.loads(res.read().decode("utf-8"))

    if "errorCode" in data:
        logging.error(f"❌ Authentication failed: {data}")
        return False

    headers = dict(res.getheaders())
    security_token = headers.get("X-SECURITY-TOKEN")
    cst_token = headers.get("CST")

    if not security_token or not cst_token:
        logging.error("❌ Missing tokens in authentication response headers.")
        return False

    logging.info("✅ Authentication Successful!")
    time.sleep(10)
    if "initial_message_sent" not in st.session_state:
        send_telegram_message("🚀 Trading Bot Started Successfully!")
        st.session_state.initial_message_sent = True
    return True


# 📌 FETCH MARKET DATA
def get_market_data(epic):
    conn = http.client.HTTPSConnection(BASE_URL)
    headers = {"X-SECURITY-TOKEN": security_token, "CST": cst_token}
    conn.request("GET", f"/api/v1/markets/{epic}", headers=headers)
    res = conn.getresponse()
    data = json.loads(res.read().decode("utf-8"))
    if "errorCode" in data:
        logging.error(f"❌ Error fetching market data for {epic}: {data}")
    return data


# 📌 FETCH HISTORICAL PRICES
def get_historical_prices(
    epic,
    resolution="MINUTE_15",
    max_points=1000,
    from_date=None,
    to_date=None,
    retries=3,
    delay=5,
):
    conn = http.client.HTTPSConnection(BASE_URL)
    headers = {"X-SECURITY-TOKEN": security_token, "CST": cst_token}

    query = f"/api/v1/prices/{epic}?resolution={resolution}&max={max_points}"

    if from_date:
        query += f"&from={from_date.isoformat()}"
    if to_date:
        query += f"&to={to_date.isoformat()}"

    attempt = 0
    while attempt < retries:
        try:
            conn.request("GET", query, headers=headers)
            res = conn.getresponse()
            data = res.read().decode("utf-8")

            if res.status != 200:
                logging.error(
                    f"❌ Error fetching historical prices for {epic}: HTTP {res.status} - {data}"
                )
                if attempt < retries - 1:
                    logging.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                attempt += 1
                continue

            data = json.loads(data)

            if "errorCode" in data:
                logging.error(f"❌ Error fetching historical prices for {epic}: {data}")
                return None

            return data
        except json.JSONDecodeError as e:
            logging.error(f"❌ JSON Decode Error: {e}")
        except Exception as e:
            logging.error(
                f"❌ Exception occurred while fetching historical prices for {epic}: {e}"
            )
        if attempt < retries - 1:
            logging.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
        attempt += 1
    return None


# 📌 CALCULATE TECHNICAL INDICATORS (EMA, RSI, VWAP)
def calculate_indicators(epic):
    historical_data = get_historical_prices(epic)
    if not historical_data:
        return None
    candles = historical_data.get("prices", [])

    if len(candles) < 100:  # Ensure there are enough data points
        logging.warning(f"Insufficient historical data points: {len(candles)}")
        return None

    # Convert to DataFrame
    df = pd.DataFrame(candles)
    df["close"] = df["closePrice"].apply(
        lambda x: float(x["ask"])
    )  # Extract close price
    df["volume"] = df["lastTradedVolume"].astype(float)  # Extract volume

    # Compute Indicators
    df["ema_9"] = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator()
    df["ema_21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    df["vwap"] = ta.volume.VolumeWeightedAveragePrice(
        high=df["highPrice"].apply(lambda x: float(x["ask"])),
        low=df["lowPrice"].apply(lambda x: float(x["ask"])),
        close=df["close"],
        volume=df["volume"],
        window=14,
    ).volume_weighted_average_price()

    # Get the latest values and handle NaN cases
    return {
        "EMA_9": df["ema_9"].iloc[-1] if not pd.isna(df["ema_9"].iloc[-1]) else None,
        "EMA_21": df["ema_21"].iloc[-1] if not pd.isna(df["ema_21"].iloc[-1]) else None,
        "RSI": df["rsi"].iloc[-1] if not pd.isna(df["rsi"].iloc[-1]) else None,
        "VWAP": df["vwap"].iloc[-1] if not pd.isna(df["vwap"].iloc[-1]) else None,
        "close": df["close"].iloc[-1] if not pd.isna(df["close"].iloc[-1]) else None,
    }


# 📌 GENERATE TRADE SIGNAL
def generate_signal(indicators):
    if indicators:
        ema_9 = indicators["EMA_9"]
        ema_21 = indicators["EMA_21"]
        rsi = indicators["RSI"]
        vwap = indicators["VWAP"]
        close = indicators["close"]

        if ema_9 > ema_21 and rsi < 30 and close > vwap:  # Buy signal
            return "BUY"
        elif ema_9 < ema_21 and rsi > 70 and close < vwap:  # Sell signal
            return "SELL"
    return None


# 📌 FETCH OPEN POSITIONS
def get_open_positions():
    conn = http.client.HTTPSConnection(BASE_URL)
    headers = {"X-SECURITY-TOKEN": security_token, "CST": cst_token}
    conn.request("GET", "/api/v1/positions", headers=headers)
    res = conn.getresponse()
    data = json.loads(res.read().decode("utf-8"))
    return data.get("positions", [])


# 📌 CLOSE POSITION FUNCTION
def close_position(deal_id):
    conn = http.client.HTTPSConnection(BASE_URL)
    payload = ""
    headers = {"X-SECURITY-TOKEN": security_token, "CST": cst_token}
    conn.request("DELETE", f"/api/v1/positions/{deal_id}", payload, headers)
    res = conn.getresponse()
    data = res.read()
    response = json.loads(data.decode("utf-8"))

    if "errorCode" in response:
        logging.error(f"❌ Error closing position for dealId {deal_id}: {response}")
        return False

    logging.info(f"✅ Position closed successfully for dealId {deal_id}: {response}")
    send_telegram_message(f"✅ Position closed successfully for dealId {deal_id}")
    return True


# 📌 EXECUTE TRADE
def place_trade(signal, epic, price):
    stop_loss = (
        price * (1 - RISK_PERCENTAGE / 100)
        if signal == "BUY"
        else price * (1 + RISK_PERCENTAGE / 100)
    )
    take_profit = (
        price * (1 + RISK_PERCENTAGE * TP_MULTIPLIER / 100)
        if signal == "BUY"
        else price * (1 - RISK_PERCENTAGE * TP_MULTIPLIER / 100)
    )

    conn = http.client.HTTPSConnection(BASE_URL)
    payload = json.dumps(
        {
            "epic": epic,
            "direction": signal,
            "size": TRADE_AMOUNT,
            "guaranteedStop": False,
            "stopLevel": stop_loss,
            "profitLevel": take_profit,
        }
    )
    headers = {
        "X-SECURITY-TOKEN": security_token,
        "CST": cst_token,
        "Content-Type": "application/json",
    }

    conn.request("POST", "/api/v1/positions", payload, headers)
    res = conn.getresponse()
    data = json.loads(res.read().decode("utf-8"))

    if "errorCode" in data:
        logging.error(f"❌ Trade failed for {epic}: {data}")
        return None

    logging.info(f"✅ Trade placed for {epic}: {data}")
    send_telegram_message(
        f"📊 Trade executed: {signal} {epic} | Entry: {price} | SL: {stop_loss} | TP: {take_profit}"
    )
    return data


# 📌 FETCH WALLET BALANCE
def get_wallet_balance():
    conn = http.client.HTTPSConnection(BASE_URL)
    headers = {"X-SECURITY-TOKEN": security_token, "CST": cst_token}
    conn.request("GET", "/api/v1/accounts", headers=headers)
    res = conn.getresponse()
    data = json.loads(res.read().decode("utf-8"))
    return data  # Return the full JSON response


# 📌 STREAMLIT DASHBOARD
def run_dashboard():
    # Check if the title and subtitle have already been displayed
    if "displayed_title" not in st.session_state:
        st.title("📈 Trading Bot Dashboard")
        st.subheader("📊 Live Market Data, Technical Indicators & Trade Execution")
        st.session_state.displayed_title = (
            True  # Set flag to indicate title has been displayed
        )

    # Use session state to track the loop count
    if "loop_count" not in st.session_state:
        st.session_state.loop_count = 0

    # Placeholder for loop count
    if "loop_count_placeholder" not in st.session_state:
        st.session_state.loop_count_placeholder = st.empty()

    # Update loop count in the UI
    st.session_state.loop_count_placeholder.markdown(
        f"🔄 **Loop Count:** {st.session_state.loop_count}"
    )

    # 📌 Fetch Market Data
    market_data = get_market_data(ASSET)
    indicators = calculate_indicators(ASSET)
    signal = generate_signal(indicators)

    # 📌 Fetch Wallet Balance
    if "wallet_balance_displayed" not in st.session_state:
        balances = get_wallet_balance()
        st.markdown(
            "<h3 style='font-size: 16px;'>💰 Wallet Balances</h3>",
            unsafe_allow_html=True,
        )
        st.session_state.wallet_balance_displayed = st.empty()

    balances = get_wallet_balance()
    if balances:
        balance_table = "<table style='font-size: 14px;'><tr><th>Account</th><th>Balance</th><th>Deposit</th><th>Profit/Loss</th><th>Available</th></tr>"
        for account in balances.get("accounts", []):
            account_name = account.get("accountName", "Unknown")
            currency = account.get("currency", "Unknown")
            symbol = account.get("symbol", "")
            balance = account.get("balance", {}).get("balance", 0)
            deposit = account.get("balance", {}).get("deposit", 0)
            profit_loss = account.get("balance", {}).get("profitLoss", 0)
            available = account.get("balance", {}).get("available", 0)
            balance_table += f"<tr><td>{account_name}</td><td>{symbol}{balance}</td><td>{symbol}{deposit}</td><td>{symbol}{profit_loss}</td><td>{symbol}{available}</td></tr>"
        balance_table += "</table>"
        st.session_state.wallet_balance_displayed.markdown(
            balance_table, unsafe_allow_html=True
        )

    # 📌 Fetch and Display Open Positions
    if "open_positions_displayed" not in st.session_state:
        open_positions = get_open_positions()
        st.markdown(
            "<h3 style='font-size: 16px;'>📊 Open Positions</h3>", unsafe_allow_html=True
        )
        st.session_state.open_positions_displayed = st.empty()

    open_positions = get_open_positions()
    if open_positions:
        positions_table = "<table style='font-size: 14px;'><tr><th>Position</th><th>Unrealized P/L</th><th>Created Date</th><th>Instrument</th></tr>"
        for position in open_positions:
            market = position.get("market", {})
            position_info = position.get("position", {})
            epic = market.get("epic", "Unknown")
            instrument_name = market.get("instrumentName", "Unknown")
            direction = position_info.get("direction", "Unknown")
            size = position_info.get("size", 0)
            level = position_info.get("level", 0)
            upl = position_info.get("upl", 0)
            created_date = position_info.get("createdDate", "Unknown")
            positions_table += f"<tr><td>{instrument_name} ({epic}) - {direction} {size} @ {level}</td><td>${upl}</td><td>{created_date}</td><td>{instrument_name}</td></tr>"
        positions_table += "</table>"
        st.session_state.open_positions_displayed.markdown(
            positions_table, unsafe_allow_html=True
        )
    else:
        st.session_state.open_positions_displayed.markdown(
            "<p style='font-size: 14px;'>No open positions.</p>", unsafe_allow_html=True
        )

    # 📌 Close Open Positions if Necessary
    open_positions = get_open_positions()
    for position in open_positions:
        market = position.get("market", {})
        position_info = position.get("position", {})
        epic = market.get("epic", "Unknown")
        direction = position_info.get("direction", "Unknown")
        level = position_info.get("level", 0)
        upl = position_info.get("upl", 0)
        deal_id = position_info.get("dealId", "Unknown")

        if epic == ASSET:
            # Example condition to close a position: if unrealized P/L is greater than a certain threshold
            if upl > 15:  # Adjust this value as needed
                close_position(deal_id)
                st.markdown(
                    f"<p style='font-size: 14px; color: green;'>✅ **Position Closed:** {epic} - {direction} {upl}</p>",
                    unsafe_allow_html=True,
                )
                # Reset the max positions message flag
                if "max_positions_message_displayed" in st.session_state:
                    del st.session_state.max_positions_message_displayed

    # 📌 Display Current Calculated Indicators
    if indicators:
        # Check if the indicators for this asset have already been displayed
        if f"indicators_displayed_{ASSET}" not in st.session_state:
            # Display indicators for the first time
            st.markdown(
                f"<h3 style='font-size: 16px;'>📈 Current Calculated Indicators for {ASSET}</h3>",
                unsafe_allow_html=True,
            )
            col1, col2, col3, col4 = st.columns(4)
            st.session_state[f"indicators_displayed_{ASSET}"] = {
                "col1": col1.empty(),
                "col2": col2.empty(),
                "col3": col3.empty(),
                "col4": col4.empty(),
            }

        # Update the indicators in place
        st.session_state[f"indicators_displayed_{ASSET}"]["col1"].markdown(
            f"<p style='font-size: 14px;'>EMA 9: {indicators['EMA_9'] if indicators['EMA_9'] is not None else 'N/A'}</p>",
            unsafe_allow_html=True,
        )
        st.session_state[f"indicators_displayed_{ASSET}"]["col2"].markdown(
            f"<p style='font-size: 14px;'>EMA 21: {indicators['EMA_21'] if indicators['EMA_21'] is not None else 'N/A'}</p>",
            unsafe_allow_html=True,
        )
        st.session_state[f"indicators_displayed_{ASSET}"]["col3"].markdown(
            f"<p style='font-size: 14px;'>RSI: {indicators['RSI'] if indicators['RSI'] is not None else 'N/A'}</p>",
            unsafe_allow_html=True,
        )
        st.session_state[f"indicators_displayed_{ASSET}"]["col4"].markdown(
            f"<p style='font-size: 14px;'>VWAP: {indicators['VWAP'] if indicators['VWAP'] is not None else 'N/A'}</p>",
            unsafe_allow_html=True,
        )

    # Generate and Execute Trade Signal
    if signal:
        open_positions = get_open_positions()
        if len(open_positions) < 5:
            price = market_data.get("snapshot", {}).get("offer", "N/A")
            if price != "N/A":
                place_trade(signal, ASSET, price)
                st.markdown(
                    f"<p style='font-size: 14px; color: green;'>✅ **Trade Executed:** {signal} at ${price} for {ASSET}</p>",
                    unsafe_allow_html=True,
                )
                send_telegram_message(f"✅ Trade Executed: {signal} at ${price} for {ASSET}")
                if "no_signal_info_displayed" in st.session_state:
                    st.session_state.no_signal_info_displayed = False
            else:
                if (
                    "price_warning_displayed" not in st.session_state
                    or not st.session_state.price_warning_displayed
                ):
                    st.markdown(
                        f"<p style='font-size: 14px; color: red;'>⚠️ No valid price for {ASSET}.</p>",
                        unsafe_allow_html=True,
                    )
                    st.session_state.price_warning_displayed = True
        else:
            if "max_positions_message_displayed" not in st.session_state:
                st.markdown(
                    "<p style='font-size: 14px; color: orange;'>⚠️ **Max Open Positions Reached. No new trades will be placed.**</p>",
                    unsafe_allow_html=True,
                )
                st.session_state.max_positions_message_displayed = True
    else:
        if (
            "no_signal_info_displayed" not in st.session_state
            or not st.session_state.no_signal_info_displayed
        ):
            st.markdown(
                "<p style='font-size: 14px; color: orange;'>📉 **No Trade Signal Generated**</p>",
                unsafe_allow_html=True,
            )
            st.session_state.no_signal_info_displayed = True

        # Increment the loop count
        st.session_state.loop_count += 1

# 📌 MAIN LOOP
if __name__ == "__main__":
    if authenticate():
        while True:
            try:
                run_dashboard()
                logging.info("***** LOOP THE SCRIPT *****")
            except Exception as e:
                logging.error(f"❌ Exception occurred in main loop: {e}")
            time.sleep(30)  # Loop every 30 seconds
