from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import random
import string
from datetime import datetime
from typing import Optional

# Initialize FastAPI app
app = FastAPI(title="CleanSpace API")

# Enable CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# --- SQL DATABASE SETUP ---
def init_db():
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (email TEXT PRIMARY KEY, name TEXT, block TEXT, room TEXT)''')
                     
        try:
            c.execute("ALTER TABLE users ADD COLUMN password TEXT")
            c.execute("UPDATE users SET password = 'password123'") 
        except sqlite3.OperationalError:
            pass 
            
        c.execute('''CREATE TABLE IF NOT EXISTS requests 
                     (req_id TEXT PRIMARY KEY, email TEXT, reason TEXT, is_emergency BOOLEAN, 
                      status TEXT, pool TEXT, staff_assigned TEXT, time_req TEXT, time_done TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS complaints 
                     (comp_id TEXT PRIMARY KEY, email TEXT, complaint_text TEXT, time_submitted TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS staff 
                     (staff_id TEXT PRIMARY KEY, name TEXT, gender TEXT)''')
                     
        try:
            c.execute("ALTER TABLE staff ADD COLUMN password TEXT")
            c.execute("UPDATE staff SET password = staff_id || '123'") 
        except sqlite3.OperationalError:
            pass 
            
        c.execute('''CREATE TABLE IF NOT EXISTS reviews 
                     (req_id TEXT PRIMARY KEY, staff_id TEXT, rating INTEGER, time_submitted TEXT)''')
        
        c.execute("SELECT COUNT(*) FROM staff")
        if c.fetchone()[0] == 0:
            initial_staff = {
                "m_01": "Suresh", "m_02": "Ramesh", "m_03": "Raj", "m_04": "Karthik", "m_05": "Vijay",
                "m_06": "Ajith", "m_07": "Kumar", "m_08": "Arun", "m_09": "Vikram", "m_10": "Surya",
                "f_01": "Priya", "f_02": "Lakshmi", "f_03": "Anjali", "f_04": "Kavya", "f_05": "Sneha",
                "f_06": "Divya", "f_07": "Swathi", "f_08": "Meena", "f_09": "Roopa", "f_10": "Bhavani"
            }
            for sid, name in initial_staff.items():
                gender = 'M' if sid.startswith('m') else 'F'
                unique_pass = f"{sid}123" 
                c.execute("INSERT INTO staff VALUES (?, ?, ?, ?)", (sid, name, gender, unique_pass))
        
        conn.commit()

init_db()

mens_blocks = ["Q", "P", "M", "N", "S", "T"]
womens_blocks = ["G", "J", "H"]

# --- DATA MODELS ---
class EmailCheck(BaseModel):
    email: str

class UserLogin(BaseModel):
    email: str
    password: str 
    name: Optional[str] = None
    block: Optional[str] = None
    room: Optional[str] = None

class RequestModel(BaseModel):
    email: str
    reason: str
    is_emergency: bool

class ComplaintModel(BaseModel):
    email: str
    complaint_text: str

class ManagerLogin(BaseModel):
    manager_id: str
    password: str

class StaffLogin(BaseModel):
    staff_id: str
    password: str

class NewStaff(BaseModel):
    name: str
    gender: str

class RatingModel(BaseModel):
    req_id: str
    staff_id: str
    rating: int

# --- API ENDPOINTS ---

# NEW: Quick check to see if student exists before asking for password
@app.post("/auth/student/check")
def check_student_email(data: EmailCheck):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE email=?", (data.email,))
        return {"exists": bool(c.fetchone())}

@app.post("/auth/student")
def student_auth(user: UserLogin):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (user.email,))
        existing_user = c.fetchone()
        
        if existing_user:
            if existing_user[4] != user.password:
                raise HTTPException(status_code=401, detail="Incorrect Password")
                
            return {
                "status": "returning", 
                "data": {"email": existing_user[0], "name": existing_user[1], "block": existing_user[2], "room": existing_user[3]}
            }
        else:
            if not user.name or not user.block or not user.room:
                raise HTTPException(status_code=400, detail="Please fill out all profile fields to create your account.")
            
            c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", (user.email, user.name, user.block, user.room, user.password))
            conn.commit()
            
            return {
                "status": "new", 
                "data": {"email": user.email, "name": user.name, "block": user.block, "room": user.room}
            }

@app.post("/auth/staff")
def staff_auth(login: StaffLogin):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("SELECT staff_id, name FROM staff WHERE staff_id=? AND password=?", (login.staff_id, login.password))
        user = c.fetchone()
        
        if user:
            return {"status": "success", "staff_id": user[0], "name": user[1]}
            
        raise HTTPException(status_code=401, detail="Invalid Staff ID or Password")

@app.post("/request")
def make_request(req: RequestModel):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("SELECT block, room FROM users WHERE email=?", (req.email,))
        user_data = c.fetchone()
        
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found.")
        
        block, room = user_data[0], user_data[1]
        
        c.execute("""
            SELECT r.req_id 
            FROM requests r
            JOIN users u ON r.email = u.email
            WHERE u.block = ? AND u.room = ? AND r.status != 'COMPLETED'
        """, (block, room))
        
        active_req = c.fetchone()
        if active_req:
            raise HTTPException(status_code=400, detail="A cleaning request is already active for your room.")
        
        pool = "MENS_POOL" if block.upper() in mens_blocks else "WOMENS_POOL"
        req_id = f"REQ_{datetime.now().strftime('%H%M%S%f')}"
        time_req = datetime.now().strftime("%I:%M %p")
        
        c.execute("INSERT INTO requests VALUES (?, ?, ?, ?, 'PENDING', ?, NULL, ?, NULL)", 
                  (req_id, req.email, req.reason, req.is_emergency, pool, time_req))
        conn.commit()
        
    return {"req_id": req_id, "status": "Added to Queue"}

@app.get("/request/{req_id}")
def get_request_status(req_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT r.status, s.name
            FROM requests r
            LEFT JOIN staff s ON r.staff_assigned = s.staff_id
            WHERE r.req_id=?
        """, (req_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Request not found")
        return {"status": row[0], "staff_name": row[1]}

@app.get("/student/history/{email}")
def get_student_history(email: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT r.req_id, r.reason, r.status, r.time_req, r.time_done, s.name, s.staff_id, rev.rating, r.is_emergency
            FROM requests r
            LEFT JOIN staff s ON r.staff_assigned = s.staff_id
            LEFT JOIN reviews rev ON r.req_id = rev.req_id
            WHERE r.email=? ORDER BY r.req_id DESC
        """, (email,))
        rows = c.fetchall()
        
    return [{
        "req_id": r[0], "reason": r[1], "status": r[2], "time_req": r[3], 
        "time_done": r[4], "staff_name": r[5], "staff_id": r[6], "rating": r[7], "is_emergency": r[8]
    } for r in rows]

@app.post("/student/rate")
def rate_service(rating: RatingModel):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        time_sub = datetime.now().strftime("%I:%M %p")
        c.execute("INSERT INTO reviews VALUES (?, ?, ?, ?)", 
                  (rating.req_id, rating.staff_id, rating.rating, time_sub))
        conn.commit()
    return {"status": "Success"}

@app.post("/student/complaint")
def submit_complaint(comp: ComplaintModel):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        comp_id = f"COMP_{datetime.now().strftime('%H%M%S%f')}"
        time_sub = datetime.now().strftime("%I:%M %p")
        
        c.execute("INSERT INTO complaints VALUES (?, ?, ?, ?)", 
                  (comp_id, comp.email, comp.complaint_text, time_sub))
        conn.commit()
    return {"status": "Complaint Submitted", "comp_id": comp_id}

@app.get("/student/complaints/{email}")
def get_student_complaints(email: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("SELECT complaint_text, time_submitted FROM complaints WHERE email=? ORDER BY comp_id DESC", (email,))
        rows = c.fetchall()
    return [{"text": r[0], "time": r[1]} for r in rows]

@app.get("/staff/pool/{staff_id}")
def get_pool(staff_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM staff WHERE staff_id=?", (staff_id,))
        if not c.fetchone():
            raise HTTPException(status_code=400, detail="Invalid Staff ID")

        pool = "MENS_POOL" if staff_id.startswith("m_") else "WOMENS_POOL"
        
        c.execute("""
            SELECT r.req_id, u.room, u.block, r.reason, r.is_emergency, r.status 
            FROM requests r JOIN users u ON r.email = u.email 
            WHERE ((r.pool=? AND r.staff_assigned IS NULL) OR r.staff_assigned=?)
            AND r.status != 'COMPLETED'
            ORDER BY r.is_emergency DESC, r.time_req ASC
        """, (pool, staff_id))
        rows = c.fetchall()
        
    return [{"req_id": r[0], "room": r[1], "block": r[2], "reason": r[3], "emergency": r[4], "status": r[5]} for r in rows]

@app.post("/staff/accept/{req_id}/{staff_id}")
def accept_job(req_id: str, staff_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        
        c.execute("SELECT req_id FROM requests WHERE staff_assigned=? AND status='ACCEPTED'", (staff_id,))
        active_job = c.fetchone()
        
        if active_job and active_job[0] != req_id:
            raise HTTPException(status_code=400, detail="You already have an active job. Please complete or pass it first.")
            
        c.execute("UPDATE requests SET status='ACCEPTED', staff_assigned=? WHERE req_id=?", (staff_id, req_id))
        conn.commit()
    return {"message": "Job Accepted"}

@app.post("/staff/pass/{req_id}")
def pass_job(req_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE requests SET status='PENDING', staff_assigned=NULL WHERE req_id=?", (req_id,))
        conn.commit()
    return {"message": "Job Passed back to Queue"}

@app.post("/complete/{req_id}")
def complete_job(req_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        time_done = datetime.now().strftime("%I:%M %p")
        c.execute("UPDATE requests SET status='COMPLETED', time_done=? WHERE req_id=?", (time_done, req_id))
        conn.commit()
    return {"message": "Job Completed!", "time": time_done}

@app.post("/auth/manager")
def manager_auth(login: ManagerLogin):
    if login.manager_id == "Admin" and login.password == "1234":
        return {"status": "success"}
    raise HTTPException(status_code=401, detail="Invalid Manager ID or Password")

@app.get("/manager/complaints")
def get_complaints():
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT u.name, u.room, u.block, c.complaint_text, c.time_submitted 
            FROM complaints c JOIN users u ON c.email = u.email ORDER BY c.comp_id DESC
        """)
        rows = c.fetchall()
    return [{"name": r[0], "room": r[1], "block": r[2], "text": r[3], "time": r[4]} for r in rows]

@app.get("/manager/staff")
def get_all_staff():
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT s.staff_id, s.name, s.gender, s.password,
                   (SELECT COUNT(*) FROM requests WHERE staff_assigned = s.staff_id AND status = 'COMPLETED') as jobs,
                   (SELECT AVG(rating) FROM reviews WHERE staff_id = s.staff_id) as avg_rating
            FROM staff s
        """)
        rows = c.fetchall()
        
    return [{"id": r[0], "name": r[1], "gender": r[2], "password": r[3], "jobs": r[4], "rating": round(r[5], 1) if r[5] else "N/A"} for r in rows]

@app.delete("/manager/staff/{staff_id}")
def remove_staff(staff_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("DELETE FROM staff WHERE staff_id=?", (staff_id,))
        conn.commit()
    return {"status": "Removed"}

@app.get("/manager/staff/{staff_id}/reviews")
def get_staff_reviews(staff_id: str):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT rev.rating, rev.time_submitted, u.room, u.block, r.reason
            FROM reviews rev
            JOIN requests r ON rev.req_id = r.req_id
            JOIN users u ON r.email = u.email
            WHERE rev.staff_id=?
            ORDER BY rev.time_submitted DESC
        """, (staff_id,))
        rows = c.fetchall()
    return [{"rating": r[0], "time": r[1], "room": r[2], "block": r[3], "reason": r[4]} for r in rows]

@app.post("/manager/staff")
def add_staff(staff: NewStaff):
    with sqlite3.connect('cleanspace.db') as conn:
        c = conn.cursor()
        prefix = 'm_' if staff.gender.upper() == 'M' else 'f_'
        
        c.execute("SELECT staff_id FROM staff WHERE staff_id LIKE ? ORDER BY staff_id DESC LIMIT 1", (prefix + '%',))
        row = c.fetchone()
        
        new_num = int(row[0].split('_')[1]) + 1 if row else 1
        new_id = f"{prefix}{new_num:02d}"
        
        chars = string.ascii_letters + string.digits
        auto_password = ''.join(random.choice(chars) for _ in range(6))
        
        c.execute("INSERT INTO staff VALUES (?, ?, ?, ?)", (new_id, staff.name, staff.gender.upper(), auto_password))
        conn.commit()
        
    return {"message": "Staff added", "staff_id": new_id, "name": staff.name, "password": auto_password}