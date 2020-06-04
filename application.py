import os
import sqlite3

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for, g
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd
app.jinja_env.globals.update(zip=zip)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# function to convert cursor object to a dict of rows(col:key, cell:val) from database
def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

# Connect to  SQLite3 database
dbb = sqlite3.connect("finance.db", check_same_thread=False)

'''
getting dict instead of tuples
https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.row_factory
'''
dbb.row_factory = dict_factory
db = dbb.cursor()

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# route displaying user portfolio and cash balance (home/portfolio - page)
@app.route("/")
@login_required
def index():
    data = []
    buyPrice = []
    # get current user
    x = session["user_id"]

    # fetchall gives all the relevant table entries
    rows = db.execute("SELECT * FROM stocks WHERE id = ?", (x,)).fetchall()
    cash = db.execute("SELECT cash FROM users WHERE id = ?", (x, )).fetchall()
    history = db.execute("SELECT symbol, t_price, shares FROM t_table WHERE id = ? AND type = 1 ORDER BY (t_time) DESC", (x,)).fetchall()
    # using rows as python dict
    for row in rows:
        data.append(lookup(row["symbol"]))
        qty = row["quantity"]
        priceSum, q = 0, 0
        for line in history:
            if row["symbol"] == line["symbol"] and qty > 0:
                lineQty = line["shares"]
                priceSum += min(qty, lineQty) * line["t_price"]
                q += min(qty, lineQty)
                qty = qty - lineQty
        buyPrice.append(priceSum/q)
    # portfolio info passed onto "home (portfolio)" route
    total = sum([data[i]["price"]* int(rows[i]["quantity"]) for i in range(len(data))])
    return render_template("index.html", holdings = rows, cash = cash[0]["cash"], data = data, total = total, buyPrice = buyPrice)

# route which enables user to buy stock (Note: user needs to provide exact stock "symbol" here)
@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    # user reached route via POST(as in by submitting a form)
    if request.method == "POST":

        # store important vals in variables
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        info = lookup(symbol)
        x = session["user_id"]

        # basic input checks (if symbol could not be looked up (means symbol is Invalid))
        if not info:
            return apology("Please enter a valid symbol (Eg. AMZN)")
        if not shares.isdigit() or int(shares) < 1:
            return apology("Please enter a valid number (Tip: Quantity only be a positve integer)")

        # fetching user info from DB
        row = db.execute("SELECT * FROM users WHERE id = ?", (x,)).fetchall()

        amount = info["price"]*int(shares)
        if amount > row[0]["cash"]:
            return apology("Transaction declined, You have insufficient funds!")

        # update transaction table "t_table"
        db.execute("INSERT INTO t_table (id, symbol, t_price, shares, t_time, name) VALUES (?,?,?,?,DATETIME(),?)",(x, symbol, info["price"], shares, info["name"]))

        # update users cash balance
        db.execute("UPDATE users SET cash = ? WHERE id = ?", (row[0]["cash"] - amount, x))

        # commit changes to db
        dbb.commit()

        # if bought stock already present with user, update quantity else insert stock into table
        stock = db.execute("SELECT * FROM stocks WHERE id = ? AND symbol = ?", (x, symbol)).fetchall()
        if len(stock) == 0:
            db.execute("INSERT INTO stocks (symbol, quantity, id) VALUES(?, ?, ?)",(symbol, shares, x))
        else:
            quantity = db.execute("SELECT * FROM stocks WHERE id = ? AND symbol = ?", (x, symbol)).fetchall()
            db.execute("UPDATE stocks SET quantity = ? WHERE id = ? AND symbol = ?", (quantity[0]["quantity"]+int(shares), x, symbol))
        dbb.commit()

        # flash success message and redirect to portfolio (home) page
        flash("%s share(s) of %s bought!" % (shares, info["name"]))
        return redirect("/")
    # user reached route via GET (as in by clicking some link or a redirect)
    else:
        return render_template("buy.html")

# route to display users transaction history
@app.route("/history")
@login_required
def history():
    # fetch transaction history info from db and pass it "history" route for display to user
    #rows = db.execute("SELECT * FROM t_table WHERE id = ? ORDER BY (t_time) DESC LIMIT 10", (session["user_id"],)).fetchall()
    rows = db.execute("SELECT id,symbol,type,t_price,shares,DATETIME(t_time,'localtime') as t_time,name FROM t_table WHERE id = ? ORDER BY (t_time) DESC LIMIT 10", (session["user_id"],)).fetchall()
    return render_template("history.html", history = rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("Please provide a username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Please provide a password")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          {"username":request.form.get("username")}).fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("Invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Welcome user and redirect to home(his portfolio) page
        flash("Welcome %s. Build your portfolio via 'Buy' stocks or cash in your profits via 'Sell'"% request.form.get("username"))
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

# route which enables stock price lookup (stock quotation)
@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    # user reached route via POST (as in by submitting a form)
    if request.method == "POST":

        # fetch requested stock info, store it in infoDict and pass it to "quoted" route
        infoDict = lookup(request.form.get("symbol"))
        if not infoDict:
            return apology("Please enter a valid symbol (Eg. GOOGL)")
        return render_template("quoted.html", info = infoDict)

    # user reached route via GET
    else:
        return render_template("quote.html")

# route for new user registration
@app.route("/register", methods=["GET", "POST"])
def register():

    # user reached route via post(submitting a form)
    if request.method == "POST":
        user = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # checks to ensure input fields are not empty
        if not user:
            return apology("Username cannot be empty")
        elif len(password) < 8:
            return apology("Password must be atleast 8 characters long")

        # checks to ensure username is unique and the password and confirmation match
        rows = db.execute("SELECT * FROM users WHERE username = ?", (user,)).fetchall()
        if len(rows):
            return apology(f"Sorry, {user} is taken, Please provide a different username")
        if password != confirmation:
            return apology("Confirmation different from password!")

        # generating a password hash (hash to be stored in DB)
        password_hash = str(generate_password_hash(password))

        # all fields are valid, insert user to db
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (user,password_hash))
        dbb.commit()

        # display success message and redirect user to home page(his portfolio page)
        flash("%s registered!" % user)
        return redirect('/')

    # user reached route via GET (as by clicking a link or a redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    # user reached route via POST (as by submitting a form)
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        x = session["user_id"]

        # searching for the selected stock in "stocks" table
        rows = db.execute("SELECT * FROM stocks WHERE id = ? AND symbol = ?",(x, symbol)).fetchall()

        # check to ensure symbol field was not empty
        if not symbol:
            return apology("No symbol was specified")

        # if no values are returned from earlier query in "stocks" table
        if not rows:
            return apology("You cannot sell stocks you don't own!")

        # basic input "quantity" criterion check
        if not shares.isdigit() or int(shares) < 1:
            return apology("Please enter a valid number (Tip: Quantity only be a positve integer)")

        # if sell order more than asset owned
        if int(shares) > rows[0]["quantity"]:
            return apology("You only own %s share(s) of %s stock" % (rows[0]["quantity"], symbol))

        # all checks satisfied, go ahead with updating the DB.
        if rows[0]["quantity"] - int(shares):   # if new quantity is non-zero
            db.execute("UPDATE stocks SET quantity = ? WHERE id = ? AND symbol = ?", (rows[0]["quantity"] - int(shares), x, symbol))
        else:                                   # if no more stocks left in account then delete from table
            db.execute("DELETE FROM stocks WHERE id = ? and symbol = ?", (x, symbol))
        dbb.commit()

        # lookup symbol to get current price info and store in DB (for history section)
        info = lookup(symbol)
        db.execute("INSERT INTO t_table (id, symbol, type, t_price, shares, t_time, name) VALUES (?,?,'0',?,?,DATETIME(),?)", (x, symbol, info["price"], shares,info["name"]))
        dbb.commit()

        # update user's cash reserve
        rows = db.execute("SELECT cash FROM users WHERE id = ?", (x,)).fetchall()
        db.execute("UPDATE users SET cash = ? WHERE id = ?", (rows[0]["cash"] + info["price"]*int(shares), x))
        dbb.commit()

        # display success message and redirect to home(portfolio) page
        flash("%s share(s) of %s sold!" % (shares, info["name"]))

        return redirect("/")
    else:
        # user reached route via GET (as in by clicking some link or a redirect)
        return render_template("sell.html")

# route to display leaderboard
@app.route("/leaderboard")
@login_required
def leaderboard():
    # storing current user id
    x = session["user_id"]

    # fetch transaction history info from db and pass it to "history" route for display to user
    users = db.execute("SELECT * FROM users").fetchall()

    # store api lookup info for all unique stocks in DB (will help save API calls!!)
    stocks = db.execute("SELECT DISTINCT symbol FROM stocks").fetchall()
    leaderboard = []
    priceDict = {}
    for stock in stocks:
        s = str(stock['symbol'])
        priceDict[s] = lookup(stock["symbol"])["price"]

    # iterating over each user to get total asset info
    for user in users:

        # storing current user's username (used to highlight user on leaderboard)
        if user["id"] == x:
            curr_user = user["username"]

        # retrieve each user's assets from table 'stocks'
        assets = db.execute("SELECT * FROM stocks WHERE id = ?", (user["id"],)).fetchall()
        cash = user["cash"]
        assetVal = 0
        for asset in assets:
            sym = str(asset["symbol"])
            assetVal += priceDict[sym] * asset["quantity"]
        total = assetVal + cash
        leaderboard.append([user["username"], assetVal, cash, total])

    # sorting leaderboard by total
    leaderboard.sort(key=lambda x : x[3], reverse=True)

    # store index of current user, personal rank to be displayed as well along with leaderboard
    for i, leader in enumerate(leaderboard):
        if curr_user in leader:
            curr_idx = i
            break
    return render_template("leaderboard.html", leaders = leaderboard, curr_idx = curr_idx)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
