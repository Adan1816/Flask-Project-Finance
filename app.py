import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

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
    rows = db.execute(
        "SELECT symbol, SUM(shares) AS shares FROM purchases WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0",
        session["user_id"]
    )

    user = db.execute(
        "SELECT cash FROM users WHERE id = ?", session["user_id"]
    )
    if not user:
        return apology("user not found", 403)
    cash = user[0]["cash"]

    holdings = []
    stocks_total = 0.0

    for row in rows:
        symbol = row["symbol"]
        shares = row["shares"]
        quote =  lookup(symbol)
        if quote is None:
            price = 0.0
            name = symbol
        else:
            price = float(quote["price"])
            name = quote["name"]
        total = shares * price
        stocks_total += total
        holdings.append({
            "symbol": symbol,
            "name": name,
            "shares": shares,
            "price": price,
            "total": total
        })
    
    grand_total = stocks_total + float(cash)

    return render_template("index.html", holdings=holdings, cash=cash, stocks_total=stocks_total, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("must provide a symbol", 403)
        
        quote = lookup(symbol)
        if quote is None:
            return apology("invalid symbol", 403)
        
        shares = request.form.get("shares")
        try:
            shares = int(shares)
        except (ValueError, TypeError):
            return apology("invalid number of shares", 403)

        if not shares>0:
            return apology("min share amount: 1", 403)

        rows = db.execute(
            "SELECT cash FROM users WHERE id = ?", session["user_id"]
        )
        if not rows:
            return apology("user not found", 403)

        cash = rows[0]["cash"] 
        total_price = quote["price"] * shares

        if total_price > cash:
            return apology("not enough balance", 403)

        try:
            db.execute(
                "UPDATE users SET cash = cash - ? WHERE id = ?",
                total_price, session["user_id"]
            )
            
            stock_data = db.execute(
                "SELECT * FROM purchases WHERE symbol = ? AND user_id = ?",
                quote["symbol"], session["user_id"]
            )
            if not stock_data:
                db.execute(
                    "INSERT INTO purchases (user_id, symbol, shares, price) VALUES (?,?,?,?)",
                    session["user_id"], quote["symbol"], shares, quote["price"]
                )
            else:
                db.execute(
                    "UPDATE purchases SET shares = shares + ? WHERE user_id = ? AND symbol = ?",
                     shares, session["user_id"], quote["symbol"]
                )
            
            db.execute(
                "INSERT INTO history (user_id, symbol, shares, price, action) VALUES (?,?,?,?,?)",
                session["user_id"], quote["symbol"], shares, quote["price"], "buy"
            )

            flash("Purchase Successful!")
            return redirect("/")
        except Exception as e:
            return apology("Transaction Failed", 403)
        
    
    else:
        return render_template("buy.html")       
        


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute(
        "SELECT * FROM history WHERE user_id = ?",
        session["user_id"]
    )

    holdings = []
    

    for row in rows:
        symbol = row["symbol"]
        shares = row["shares"]
        quote =  lookup(symbol)
        if quote is None:
            price = 0.0
            name = symbol
        else:
            price = float(quote["price"])
            name = quote["name"]
        total = shares * price
        
        time = row["timestamp"]
        action = row["action"]

        holdings.append({
            "symbol": symbol,
            "name": name,
            "shares": shares,
            "price": price,
            "total": total,
            "time": time,
            "action": action
        })

    return render_template("history.html", holdings=holdings)


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
    if request.method == "GET":
        
        return render_template("quote.html")
    
    else:
        symbol = request.form.get("symbol")
        quote_value = lookup(symbol)
        print(f"Lookup result: {quote_value}")
        return render_template("quoted.html", quote=quote_value)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        if not username:
            return apology("invalid username", 403)
        password = request.form.get("password")
        if not password:
            return apology("invalid password", 403)
        confirmation = request.form.get("confirmation")
        if not confirmation:
            return apology("invalid password")
        if password != confirmation:
            return apology("passwords do not match", 403)
        
        pw_hash = generate_password_hash(password)
        
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, pw_hash)
        return redirect("/login")
    
    else:
       
       return render_template("register.html")
    
    


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        symbols = db.execute(
            "SELECT symbol, SUM(shares) AS shares FROM purchases WHERE user_id = ? GROUP BY symbol HAVING SUM (shares) > 0",
            session["user_id"]
        )
        return render_template("sell.html", symbols=symbols)
    
    symbol = request.form.get("symbol")
    if not symbol:
        return apology("must select a symbol", 403)
    
    owned = db.execute(
        "SELECT COALESCE(SUM(shares), 0) AS shares FROM purchases WHERE user_id=? AND symbol=?",
        session["user_id"], symbol.upper() 
    )
    owned_shares = owned[0]["shares"] if owned else 0

    shares = request.form.get("shares")
    try:
        shares = int(shares)
    except (ValueError, TypeError):
        return apology("Invalid Number of Shares", 403)
    
    if shares<= 0:
        return apology("Enter a positive integer", 403)
    
    if shares > owned_shares:
        return apology("You Don't Own Enough Shares", 403)
    
    quote = lookup(symbol)
    price = float(quote["price"])
    proceeds = price * shares
    rem_shares = owned_shares - shares

    db.execute(
        "UPDATE users SET cash = cash + ? WHERE id = ?",
        proceeds, session["user_id"]
    )

    query = f"UPDATE purchases SET shares = {rem_shares} WHERE user_id = {session['user_id']} AND symbol = {symbol.upper()}"
    print(query)
    
    db.execute(
        "UPDATE purchases SET shares = ? WHERE user_id = ? AND symbol = ?",
        rem_shares, session["user_id"], symbol.upper()
    )

    db.execute(
        "INSERT INTO history (user_id, symbol, shares, price, action) VALUES (?,?,?,?,?)",
        session["user_id"], quote["symbol"], shares, quote["price"], "sell"
    )
    
    return redirect("/")
