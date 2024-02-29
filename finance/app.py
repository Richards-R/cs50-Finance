import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
import datetime
import pytz

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Find username with user id from users, then use it to find balance
    name = db.execute("SELECT username FROM users WHERE id = ?;", session['user_id'])
    account_name = name[0]['username']

    # Sum total buy and sell positions to find current balance
    buys = db.execute(
        "SELECT ticker, SUM(units), SUM(total_cost) FROM transactions WHERE buy_sell = 'buy' AND username = ? GROUP BY ticker;", account_name)
    sells = db.execute(
        "SELECT ticker, SUM(units), SUM(total_cost) FROM transactions WHERE buy_sell = 'sell' AND username = ? GROUP BY ticker;", account_name)

    total_units = 0
    position = {}
    total_pos_val = 0
    pos_arr = []

    for buy in buys:
        total_units = buy['SUM(units)']
        current_price = lookup(buy['ticker'])
        pos_value = current_price['price'] * total_units
        position = {
            'ticker': buy['ticker'],
            'price': usd(current_price['price']),
            'units': total_units,
            'pos_value': usd(pos_value),
            'p_value': pos_value,
        }
        pos_arr.append(position)
        for sell in sells:
            if buy['ticker'] == sell['ticker']:
                total_units = buy['SUM(units)'] - sell['SUM(units)']
                current_price = lookup(buy['ticker'])
                pos_value = current_price['price'] * total_units
                position.update({
                    'ticker': buy['ticker'],
                    'price': usd(current_price['price']),
                    'units': total_units,
                    'pos_value': usd(pos_value),
                    'p_value': pos_value,
                })

    pos_arr = [entry for entry in pos_arr if not entry.get('units') == 0]

    cash_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    cash = cash_balance[0]['cash']

    for pos in pos_arr:
        total_pos_val = total_pos_val + pos['p_value']

    grand_total = total_pos_val + cash

    return render_template("account.html", account_name=account_name, positions=pos_arr, cash=usd(cash), grand_total=usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    sess_id = session["user_id"]

    if request.method == "GET":
        return render_template("buy.html")
    else:
        fl_units = 0.0
        name = db.execute("SELECT username FROM users WHERE id = ?", sess_id)
        name = name[0]['username']
        date_time = datetime.datetime.now(pytz.timezone("US/Eastern"))
        ticker = request.form.get("symbol")
        units = request.form.get("shares")
        symbol = lookup(ticker)
        if not type(units) is str:
            fl_units = float(units)
        if not type(int(fl_units)) is int or not units.isdigit() or not symbol:
            flash(f"Sorry but \"{ticker}\" is not a valid ticker! Here's a Wonka Bar to enjoy while you find the right one!")
            return redirect("/buy", 400)
        price = symbol['price']
        tick = symbol['symbol']
        funds = db.execute("SELECT cash FROM users WHERE id = ?", sess_id)
        balance = funds[0]['cash']
        total_cost = price * int(units)
        if total_cost > balance:
            flash(
                f"Sorry but you don't have enough funds to place this order of {units} unit/s of {tick}! Here's a Wonka Bar to make you feel better!")
            return redirect("/buy", 400)
        balance_remaining = balance - total_cost
        buy_sell = "buy"

        db.execute("INSERT INTO transactions (date_time, username, ticker, units, price, total_cost, balance_remaining, buy_sell) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   date_time, name, ticker.upper(), units, price, total_cost, balance_remaining, buy_sell)
        db.execute("UPDATE users SET cash= ? WHERE username = ?", balance_remaining, name)
        # Redirect user to home page
        flash(f"Congratulations! You bought {units} unit/s of {tick}. Here's a Wonka bar for you!")
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    name = db.execute("SELECT username FROM users WHERE id = ?;", session['user_id'])
    account_name = name[0]['username']

    history = db.execute(
        "SELECT date_time, buy_sell, ticker, units, price, total_cost FROM transactions WHERE username = ?;", account_name)

    for trade in history:
        trade.update({
            'date_time': trade['date_time'][:10],
            'price': usd(trade['price']),
            'total_cost': usd(trade['total_cost']),
        })

    return render_template("history.html", account_name=account_name, history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        session["username"] = rows[0]["username"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    ticker = request.form.get("symbol")
    if request.method == "GET":
        return render_template("quote.html")
    else:
        result = lookup(ticker)
        if not result:
            flash('Please enter a valid ticker')
            return redirect("/quote", 400)
        result.update({
            'price': usd(result['price'])
        })
        return render_template("quoted.html", ticker=result)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        name = request.form.get("username")
        pass1 = request.form.get("password")
        pass2 = request.form.get("confirmation")
        if not name or not pass1 or not pass2:
            flash('Please enter all required fields')
            return redirect("/register", 400)

        name_exists = db.execute("SELECT * FROM users WHERE username = ?", name)

        if not name:
            flash('Please enter a username')
            return redirect("/register", 400)
        if pass1 != pass2:
            flash('Passwords do not match')
            return redirect("/register", 400)
        if name_exists:
            flash('Username "' + name + '" already in use. Please enter a new username')
            return redirect("/register", 400)

        hashed_pass = generate_password_hash(pass1, method='scrypt', salt_length=16)

        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", name, hashed_pass)

        return render_template("reg_success.html", name=name)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    name = db.execute("SELECT username FROM users WHERE id = ?;", session['user_id'])
    account_name = name[0]['username']

    if request.method == "GET":

        # Sum total buy and sell positions to find current balance
        buys = db.execute(
            "SELECT ticker, SUM(units), SUM(total_cost) FROM transactions WHERE buy_sell = 'buy' AND username = ? GROUP BY ticker;", account_name)
        sells = db.execute(
            "SELECT ticker, SUM(units), SUM(total_cost) FROM transactions WHERE buy_sell = 'sell' AND username = ? GROUP BY ticker;", account_name)

        total_units = 0
        position = {}
        total_pos_val = 0
        pos_arr = []

        for buy in buys:
            total_units = buy['SUM(units)']
            current_price = lookup(buy['ticker'])
            pos_value = current_price['price'] * total_units
            position = {
                'ticker': buy['ticker'],
                'price': usd(current_price['price']),
                'units': total_units,
                'pos_value': usd(pos_value),
                'p_value': pos_value,
            }
            pos_arr.append(position)
            for sell in sells:
                if buy['ticker'] == sell['ticker']:
                    total_units = buy['SUM(units)'] - sell['SUM(units)']
                    current_price = lookup(buy['ticker'])
                    pos_value = current_price['price'] * total_units
                    position.update({
                        'ticker': buy['ticker'],
                        'price': usd(current_price['price']),
                        'units': total_units,
                        'pos_value': usd(pos_value),
                        'p_value': pos_value,
                    })

        pos_arr = [entry for entry in pos_arr if not entry.get('units') == 0]

        cash_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = cash_balance[0]['cash']
        for pos in pos_arr:
            total_pos_val = total_pos_val + pos['p_value']

        grand_total = total_pos_val + cash

        return render_template("sell.html", account_name=account_name, positions=pos_arr, cash=usd(cash), grand_total=usd(grand_total))
    else:

        # Submit new sell order for shares
        date_time = datetime.datetime.now(pytz.timezone("US/Eastern"))
        sell_units = request.form.get("shares")
        sell_ticker = request.form.get("symbol")
        if sell_units == None:
            sell_units = request.form.get("units")
            sell_ticker = request.form.get("ticker")

        total_units = 0
        buys_units_total = db.execute("SELECT SUM(units) FROM transactions WHERE buy_sell = 'buy' AND ticker = ?;", sell_ticker)
        sells_units_total = db.execute("SELECT SUM(units) FROM transactions WHERE buy_sell = 'sell' AND ticker = ?;", sell_ticker)

        if sells_units_total[0]['SUM(units)'] != None:
            total_units = buys_units_total[0]['SUM(units)'] - sells_units_total[0]['SUM(units)']
        elif buys_units_total[0]['SUM(units)'] != None:
            total_units = buys_units_total[0]['SUM(units)']

        if int(sell_units) > total_units:
            flash(
                f"You are trying to sell more than the {total_units} units you own of {sell_ticker}! Here's a Wonka bar for you to enjoy while you choose a lower number of shares!")
            return redirect("/sell", 400)

        sell_price = lookup(sell_ticker)
        sell_value = int(sell_units) * sell_price['price']
        buy_sell = "sell"

        presell_balance = db.execute("SELECT cash FROM users WHERE username = ?", account_name)
        new_balance = presell_balance[0]['cash'] + sell_value
        db.execute("UPDATE users SET cash= ? WHERE username = ?", new_balance, account_name)
        db.execute("INSERT INTO transactions (date_time, username, ticker, units, price, total_cost, balance_remaining, buy_sell) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   date_time, account_name, sell_ticker, sell_units, sell_price['price'], sell_value, new_balance, buy_sell)

        # Redirect user to index form
        return redirect("/")
