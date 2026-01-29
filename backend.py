import pymysql
import os
import random
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from datetime import date

load_dotenv()

# ================= DB CONNECTION =================

def get_db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor,
        ssl={"ssl": {}}  # required for Aiven
    )

# ================= SEND OTP EMAIL =================

def send_otp_email(email):
    otp = random.randint(100000, 999999)

    conn = get_db_connection()
    cursor = conn.cursor()

    # delete old OTP
    cursor.execute("DELETE FROM otp_verification WHERE email=%s", (email,))

    # insert new OTP
    cursor.execute(
        "INSERT INTO otp_verification (email, otp) VALUES (%s, %s)",
        (email, otp)
    )

    conn.commit()
    conn.close()

    # email config from .env
    sender_email = os.getenv("EMAIL_USER")
    app_password = os.getenv("EMAIL_PASS")

    msg = MIMEText(f"Your OTP for Smart Expense Guard is: {otp}")
    msg["Subject"] = "Smart Expense Guard - OTP Verification"
    msg["From"] = sender_email
    msg["To"] = email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, email, msg.as_string())
        server.quit()
        return {"status": "success", "msg": "OTP sent successfully"}
    except Exception as e:
        return {"status": "error", "msg": f"Email failed: {str(e)}"}

# ================= OTP VERIFY + LOGIN =================

def verify_otp_and_login(email, otp):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM otp_verification 
        WHERE email=%s AND otp=%s 
        AND created_at >= NOW() - INTERVAL 5 MINUTE
        ORDER BY created_at DESC LIMIT 1
        """,
        (email, otp)
    )

    otp_row = cursor.fetchone()

    if not otp_row:
        conn.close()
        return {"status": "error", "msg": "Invalid or Expired OTP"}

    # delete OTP after verification
    cursor.execute("DELETE FROM otp_verification WHERE id=%s", (otp_row["id"],))
    conn.commit()

    # check user
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO users (email) VALUES (%s)", (email,))
        conn.commit()
        user_id = cursor.lastrowid
    else:
        user_id = user["user_id"]

    conn.close()
    return {"status": "success", "user_id": user_id}

# ================= ADD PERSONAL EXPENSE =================

def add_personal_expense(user_id, amount, category, description=""):
    conn = get_db_connection()
    cursor = conn.cursor()

    sql = """
        INSERT INTO expenses (user_id, amount, category, description, expense_date)
        VALUES (%s, %s, %s, %s, %s)
    """

    cursor.execute(sql, (user_id, amount, category, description, date.today()))
    conn.commit()
    conn.close()

    return {"status": "success", "msg": "Expense added"}

# ================= GET USER EXPENSES =================

def get_user_expenses(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM expenses WHERE user_id=%s ORDER BY expense_date DESC",
        (user_id,)
    )

    data = cursor.fetchall()
    conn.close()
    return data

# ================= TOTAL EXPENSE =================

def get_total_spend(user_id):
    expenses = get_user_expenses(user_id)
    return sum(float(e["amount"]) for e in expenses)

# ================= DELETE CURRENT MONTH EXPENSES =================

def delete_current_month_expenses(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM expenses 
        WHERE user_id=%s 
        AND MONTH(expense_date)=MONTH(CURDATE()) 
        AND YEAR(expense_date)=YEAR(CURDATE())
    """, (user_id,))

    conn.commit()
    conn.close()

    return {"status": "success", "msg": "Current month data deleted"}

# ================= DELETE EXPENSE =================

def delete_expense(expense_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM expenses WHERE expense_id=%s", (expense_id,))
    conn.commit()
    conn.close()

    return {"status": "success"}

# ================= UPDATE EXPENSE =================

def update_expense(expense_id, amount, category, description):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        UPDATE expenses 
        SET amount=%s, category=%s, description=%s
        WHERE expense_id=%s
    """

    cursor.execute(query, (amount, category, description, expense_id))
    conn.commit()
    conn.close()

    return {"status": "success", "msg": "Expense updated successfully"}
