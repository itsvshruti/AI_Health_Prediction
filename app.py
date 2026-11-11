
import os
import re
import math
import sqlite3
from pathlib import Path
from datetime import datetime, date

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from dotenv import load_dotenv
from google import genai


# Project configuration
BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "patients.db"

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret-key")


# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = None

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)


# Database connection
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# Create patient table
def create_table():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            dob TEXT NOT NULL,
            email TEXT NOT NULL,
            glucose REAL NOT NULL,
            haemoglobin REAL NOT NULL,
            cholesterol REAL NOT NULL,
            remarks TEXT
        )
    """)

    conn.commit()
    conn.close()


# Generate AI remarks using Gemini
def generate_ai_remarks(glucose, haemoglobin, cholesterol):

    if client is None:
        return "AI remarks unavailable: Gemini API key is not configured."


    prompt = f"""
You are a responsible AI health information assistant.

Analyze these blood test values using the specified units:

Glucose: {glucose} mg/dL
Haemoglobin: {haemoglobin} g/dL
Total Cholesterol: {cholesterol} mg/dL

IMPORTANT RULES:
- Always use the specified units.
- Do not ask for units.
- Do not consider patient sex, age or medical history.
- Do not diagnose any disease.
- Do not prescribe medicines or supplements.
- Use commonly accepted adult reference information.
- Clearly explain limitations where test context is missing.
- Do not make unsupported health claims.

Provide the report in this format:

1. GLUCOSE ANALYSIS:
Explain the value and its possible significance.
Mention that fasting, random and post-meal glucose
have different interpretations.

2. HAEMOGLOBIN ANALYSIS:
Explain the value using general adult reference
information. Mention that interpretation may vary.

3. CHOLESTEROL ANALYSIS:
Explain the total cholesterol value and its possible
cardiovascular significance. Mention that a complete
lipid profile gives a better assessment.

4. HEALTH SUGGESTIONS:
Give 3-4 practical suggestions about:
- Balanced meals and healthy food choices.
- Physical activity and regular exercise.
- Limiting sugary drinks and highly processed foods.
- Appropriate follow-up blood testing when needed.

5. MEDICAL RECOMMENDATION:
Explain which results may need further evaluation
and recommend consulting a qualified healthcare
professional.

Use clear, simple and patient-friendly language.
Avoid frightening the patient.
Do not claim that lifestyle changes can replace treatment.

End with:
"This report is for educational purposes only and
is not a medical diagnosis."
Keep the complete report within 180 words.
"""



    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )

        remarks = response.text

        if remarks and remarks.strip():
            print("Gemini generated remarks:", remarks.strip())
            return remarks.strip()

        print("Gemini returned an empty response.")
        return "Gemini did not return a remark. Please try again."

    except Exception as error:
        print("Gemini API error:", error)

        return (
            "AI remarks are temporarily unavailable. "
            "Please try again later."
        )


# Validate patient details
def validate_patient(form):

    name = form.get("full_name", "").strip()
    dob = form.get("dob", "").strip()
    email = form.get("email", "").strip()

    glucose_text = form.get("glucose", "").strip()
    haemoglobin_text = form.get("haemoglobin", "").strip()
    cholesterol_text = form.get("cholesterol", "").strip()

    if not all([
        name,
        dob,
        email,
        glucose_text,
        haemoglobin_text,
        cholesterol_text
    ]):
        return None, "Please fill in all fields."

    # Email validation
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return None, "Please enter a valid email address."

    # DOB validation
    try:
        dob_date = datetime.strptime(dob, "%d/%m/%Y").date()

        if dob_date > date.today():
            return None, "Date of birth cannot be in the future."

    except ValueError:
        return None, "Enter a valid DOB in dd/mm/yyyy format."

    # Blood value validation
    try:
        glucose = float(glucose_text)
        haemoglobin = float(haemoglobin_text)
        cholesterol = float(cholesterol_text)

        values = [glucose, haemoglobin, cholesterol]

        if any(
            not math.isfinite(value) or value < 0
            for value in values
        ):
            raise ValueError

    except (ValueError, TypeError):
        return None, "Blood values must be valid non-negative numbers."

    return {
        "full_name": name,
        "dob": dob,
        "email": email,
        "glucose": glucose,
        "haemoglobin": haemoglobin,
        "cholesterol": cholesterol
    }, None


# Display all patient records
@app.route("/")
def home():

    conn = get_db_connection()

    patients = conn.execute(
        "SELECT * FROM patients ORDER BY id"
    ).fetchall()

    conn.close()

    return render_template("index.html", patients=patients)


# Add patient
@app.route("/add", methods=["POST"])
def add_patient():

    print("ADD PATIENT ROUTE CALLED")

    data, error = validate_patient(request.form)

    if error:
        flash(error)
        return redirect(url_for("home"))

    remarks = generate_ai_remarks(
        data["glucose"],
        data["haemoglobin"],
        data["cholesterol"]
    )

    conn = get_db_connection()

    conn.execute("""
        INSERT INTO patients
        (full_name, dob, email, glucose, haemoglobin, cholesterol, remarks)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data["full_name"],
        data["dob"],
        data["email"],
        data["glucose"],
        data["haemoglobin"],
        data["cholesterol"],
        remarks
    ))

    conn.commit()
    conn.close()

    flash("Patient added successfully!")

    return redirect(url_for("home"))


# Edit patient
@app.route("/edit/<int:patient_id>", methods=["GET", "POST"])
def edit_patient(patient_id):

    conn = get_db_connection()

    patient = conn.execute(
        "SELECT * FROM patients WHERE id = ?",
        (patient_id,)
    ).fetchone()

    if patient is None:
        conn.close()
        flash("Patient record not found.")
        return redirect(url_for("home"))

    if request.method == "POST":

        data, error = validate_patient(request.form)

        if error:
            conn.close()
            flash(error)
            return redirect(
                url_for("edit_patient", patient_id=patient_id)
            )

        remarks = generate_ai_remarks(
            data["glucose"],
            data["haemoglobin"],
            data["cholesterol"]
        )

        conn.execute("""
            UPDATE patients
            SET full_name = ?,
                dob = ?,
                email = ?,
                glucose = ?,
                haemoglobin = ?,
                cholesterol = ?,
                remarks = ?
            WHERE id = ?
        """, (
            data["full_name"],
            data["dob"],
            data["email"],
            data["glucose"],
            data["haemoglobin"],
            data["cholesterol"],
            remarks,
            patient_id
        ))

        conn.commit()
        conn.close()

        flash("Patient updated successfully!")

        return redirect(url_for("home"))

    conn.close()

    return render_template("edit.html", patient=patient)


# Delete patient
@app.route("/delete/<int:patient_id>", methods=["POST"])
def delete_patient(patient_id):

    conn = get_db_connection()

    conn.execute(
        "DELETE FROM patients WHERE id = ?",
        (patient_id,)
    )

    conn.commit()
    conn.close()

    flash("Patient deleted successfully!")

    return redirect(url_for("home"))


# Run application
if __name__ == "__main__":

    create_table()

    app.run(debug=True)
