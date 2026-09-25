from flask import Flask, render_template,redirect, session, Response, url_for, flash, request, jsonify
import numpy as np
import os
from werkzeug.utils import secure_filename
import uuid
from werkzeug.security import generate_password_hash
import mysql.connector
from hashlib import sha256
from datetime import time,date, datetime
from flask import  get_flashed_messages
import pandas as pd
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)
app.secret_key = 'ashbdbdb'


# MySQL config
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'chatbot'                                                              
}

def get_db_connection():
    return mysql.connector.connect(**db_config)
       
def hash_password(password):
    return sha256(password.encode()).hexdigest()


genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

TOTAL_QUESTIONS = 5


def generate_all_questions(domain):
    prompt = f"""
    You are a professional technical interviewer.
    Generate exactly {TOTAL_QUESTIONS} interview questions
    for the domain: {domain}.
    Return ONLY a numbered list.
    """

    response = model.generate_content(prompt)
    lines = response.text.split("\n")

    questions = [
        re.sub(r"^\d+[\.\)]\s*", "", q.strip())
        for q in lines if q.strip() and len(q.strip()) > 10
    ]

    if len(questions) < TOTAL_QUESTIONS:
        raise ValueError("Insufficient questions generated")

    return questions[:TOTAL_QUESTIONS]



def evaluate_answer_locally(answer):
    answer = answer.lower()
    length_score = min(len(answer.split()) // 10, 5)
    keyword_score = 3 if any(k in answer for k in ["example", "because", "use", "benefit"]) else 1
    return min(length_score + keyword_score, 10)

# ---------------- GEMINI FINAL EVALUATION ----------------
def evaluate_full_interview(domain, qa_list):
    total_questions = len(qa_list)

    prompt = f"""
    You are a technical interviewer.

    Evaluate the interview for domain: {domain}.

    Respond ONLY with valid JSON (no explanation, no markdown).

    JSON format:
    {{
      "status": "Excellent | Good | Needs Improvement",
      "strengths": ["..."],
      "improvements": ["..."],
      "questions": [
        {{
          "question": "...",
          "feedback": "...",
          "score": 0-10
        }}
      ],
      "final_feedback": "summary"
    }}

    IMPORTANT:
    - Give score (0–10) for EACH question
    - Do NOT calculate total score
    """

    for qa in qa_list:
        prompt += f"\nQ: {qa['question']}\nA: {qa['answer']}\n"

    response = model.generate_content(prompt)
    raw_text = response.text.strip()

    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError("Gemini did not return valid JSON")

    result = json.loads(match.group())

    # ✅ CALCULATE OVERALL SCORE LOCALLY
    total_score = sum(q.get("score", 0) for q in result.get("questions", []))

    # 🔒 Clamp score
    max_score = total_questions * 10
    total_score = min(total_score, max_score)

    result["overall_score"] = total_score
    result["total_marks"] = max_score

    return result

# ---------------- SAVE RESULT ----------------
def save_result(user_id, domain, score, status, feedback):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO interview_results
        (user_id, domain, score, status, feedback, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        user_id,
        domain,
        score,
        status,
        json.dumps(feedback),
        datetime.now()
    ))
    conn.commit()
    cur.close()
    conn.close()



@app.route("/")
def index():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/history")
def history():
    # 🔒 Login check
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # ---- fetch ONLY current user's interview history ----
    cur.execute("""
        SELECT id,domain, score, feedback, status, created_at
        FROM interview_results
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))

    rows = cur.fetchall()

    history_data = []
    scores = []
    domains = set()

    for row in rows:
        feedback_json = json.loads(row["feedback"])

        scores.append(row["score"])
        domains.add(row["domain"])

        history_data.append({
            "id": row["id"],
            "domain": row["domain"],
            "score": row["score"],
            "status": row["status"],
            "date": row["created_at"],
            "strengths": feedback_json.get("strengths", []),
            "improvements": feedback_json.get("improvements", []),
            "questions": feedback_json.get("questions", []),
            "final_feedback": feedback_json.get("final_feedback", "")
        })

    # ---- stats calculation ----
    total_interviews = len(scores)

    avg_score = int(sum(scores) / total_interviews) if scores else 0

    domains_covered = len(domains)

    improvement_rate = 0
    if len(scores) >= 2 and scores[-1] > 0:
        improvement_rate = int(((scores[0] - scores[-1]) / scores[-1]) * 100)

    cur.close()
    conn.close()

    return render_template(
        "history.html",
        history=history_data,
        total_interviews=total_interviews,
        avg_score=avg_score,
        domains_covered=domains_covered,
        improvement_rate=improvement_rate
    )

@app.route("/delete-history/<int:history_id>", methods=["DELETE"])
def delete_history(history_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    # 🔒 Delete ONLY user's own record
    cur.execute("""
        DELETE FROM interview_results
        WHERE id = %s AND user_id = %s
    """, (history_id, user_id))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True})



@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check existing email
        cursor.execute("SELECT u_id FROM user WHERE email=%s", (email,))
        existing = cursor.fetchone()

        if existing:
            conn.close()
            flash("Email already exists.", "error")
            return redirect(url_for('register'))

        # Insert user
        hashed_password = hash_password(password)
        cursor.execute(
            "INSERT INTO user (uname, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed_password)
        )
        conn.commit()
        conn.close()

        flash("Registration Successful! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')



@app.route("/login", methods=['GET', 'POST'])
def login():
    show_logout = session.pop('show_logout_msg', False)

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM user WHERE email=%s", (email,))
        user = cursor.fetchone()

        conn.close()

        if user and hash_password(password) == user['password']:
            session['user_id'] = user['u_id']
            session['username'] = user['uname']
            session['uemail'] = user['email']

            flash("Login Successful!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid email or password.", "error")
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route("/select-domain/<domain>")
def select_domain(domain):
    try:
        if "user_id" not in session:
            return redirect(url_for("login"))

        session.pop("final_result", None)

        session["domain"] = domain.capitalize()
        session["q_index"] = 0
        session["total_score"] = 0
        session["answers"] = []
        session["questions"] = generate_all_questions(domain)

        return redirect(url_for("chatbot"))

    except Exception as e:
        print("❌ Error:", e)
        flash("AI service unavailable", "error")
        return redirect(url_for("index"))







@app.route("/chatbot")
def chatbot():
    if "domain" not in session or "questions" not in session:
        return redirect(url_for("index"))

    # 🔒 If interview already finished, reset index
    if session.get("q_index", 0) >= len(session.get("questions", [])):
        return redirect(url_for("select_domain", domain=session["domain"].lower()))

    return render_template("chatbot.html", domain=session["domain"])



@app.route("/get-question")
def get_question():
    q_index = session.get("q_index", 0)
    questions = session.get("questions", [])

    if not questions or q_index >= len(questions):
        return jsonify({"end": True})

    question = questions[q_index]
    session["current_question"] = question

    return jsonify({
        "question": question,
        "number": q_index + 1
    })





@app.route("/submit-answer", methods=["POST"])
def submit_answer():
    data = request.get_json()
    answer = data.get("answer", "").strip()

    if not answer:
        return jsonify({"error": "Empty answer"}), 400

    question = session.get("current_question")
    if not question:
        return jsonify({"error": "Session expired"}), 400

    # 🔒 SAFETY CHECK
    if "answers" not in session:
        session["answers"] = []

    score = evaluate_answer_locally(answer)

    session["answers"].append({
        "question": question,
        "answer": answer,
        "score": score
    })

    session["total_score"] += score
    session["q_index"] += 1

    return jsonify({"score": score})




@app.route("/final-result")
def final_result():
    # 🔒 Login check
    if "user_id" not in session or "domain" not in session:
        return redirect(url_for("login"))

    # ✅ Return cached result if exists
    if "final_result" in session:
        return render_template(
            "result.html",
            domain=session["domain"],
            result=session["final_result"],
            total_marks=len(session.get("answers", [])) * 10
        )

    domain = session["domain"]
    answers = session.get("answers", [])
    user_id = session["user_id"]
    total_marks = len(answers) * 10

    try:
        result = evaluate_full_interview(domain, answers)

        # Normalize score to total marks
        if result.get("overall_score", 0) <= 100:
            result["overall_score"] = int(
                (result["overall_score"] / 100) * total_marks
            )

    except Exception as e:
        print("❌ AI Error:", e)
        result = {
            "overall_score": 0,
            "status": "AI Error",
            "strengths": [],
            "improvements": [],
            "questions": [],
            "final_feedback": "AI service unavailable. Please try again later."
        }

    # 🔥 Cache result in session
    session["final_result"] = result

    # 💾 Save result for the CURRENT USER
    save_result(
        user_id=user_id,
        domain=domain,
        score=result["overall_score"],
        status=result["status"],
        feedback=result
    )

    return render_template(
        "result.html",
        domain=domain,
        result=result,
        total_marks=total_marks
    )



@app.route("/logout")
def logout():
    session.clear()
    session['show_logout_msg'] = True  # flag to show once
    return redirect(url_for('index'))


if __name__ == "__main__":
    app.run(debug=True)
