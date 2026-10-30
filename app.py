from flask import Flask,render_template,request,Response,redirect,url_for,session
import secrets
import os
import ast

from dotenv import load_dotenv

load_dotenv()

app=Flask(__name__)
app.secret_key=os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
from werkzeug.utils import secure_filename
from datetime import datetime

UPLOAD_FOLDER = 'static/uploads/events'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# --------------------------- MySQL persistence layer ---------------------------
# Configure MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
# and FLASK_SECRET_KEY in your environment before starting the application.
import mysql.connector
from mysql.connector import Error

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "mits_club"),
    "autocommit": False,
}

def get_connection():
    return mysql.connector.connect(**MYSQL_CONFIG)

def _rows(cursor, sql, params=()):
    cursor.execute(sql, params)
    return cursor.fetchall()

def _replace_rows(conn, table, columns, rows):
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {table}")
    if rows:
        marks = ",".join(["%s"] * len(columns))
        cur.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({marks})", rows)
    cur.close()


def _sync_rows(conn, table, columns, rows, key_column):
    cur = conn.cursor()
    keys = [row[columns.index(key_column)] for row in rows]
    if keys:
        marks = ",".join(["%s"] * len(keys))
        cur.execute(f"DELETE FROM {table} WHERE {key_column} NOT IN ({marks})", keys)
    else:
        cur.execute(f"DELETE FROM {table}")
    if rows:
        marks = ",".join(["%s"] * len(columns))
        updates = ",".join([f"{c}=VALUES({c})" for c in columns if c != key_column])
        sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({marks}) ON DUPLICATE KEY UPDATE {updates}"
        cur.executemany(sql, rows)
    cur.close()

def load_users():
    conn=get_connection(); cur=conn.cursor(dictionary=True)
    try:
        users={}
        for r in _rows(cur,"SELECT email,name,col_id,password_hash,skill,intrest,branch,year,role,created_at,github,linkedin,instagram FROM users"):
            users[r['email']]={k:v for k,v in r.items() if k!='email'}
            for field in ('skill','intrest'):
                value=users[r['email']].get(field)
                if isinstance(value,str) and value.startswith(('[]','[', '(')):
                    try: users[r['email']][field]=ast.literal_eval(value)
                    except (ValueError,SyntaxError): pass
            if users[r['email']].get('created_at') is not None: users[r['email']]['created_at']=str(users[r['email']]['created_at'])
            users[r['email']]['enrolled_clubs']=[]; users[r['email']]['enrolled_events']=[]
        for r in _rows(cur,"SELECT user_email,club_id FROM club_memberships"):
            if r['user_email'] in users: users[r['user_email']]['enrolled_clubs'].append(r['club_id'])
        for r in _rows(cur,"SELECT user_email,event_id FROM event_registrations"):
            if r['user_email'] in users: users[r['user_email']]['enrolled_events'].append(r['event_id'])
        return users
    finally: cur.close(); conn.close()

def save_users(users):
    conn=get_connection()
    try:
        cur=conn.cursor()
        user_rows=[]; member_rows=[]; registration_rows=[]
        for email,u in users.items():
            # Store the password as plain text (as requested).
            pwd=u.get('password_hash') or u.get('password') or ''
            skill=u.get('skill',''); interests=u.get('intrest','')
            if isinstance(skill,(list,tuple)): skill=repr(skill)
            if isinstance(interests,(list,tuple)): interests=repr(interests)
            user_rows.append((email,u.get('name','User'),u.get('col_id'),pwd,skill,interests,u.get('branch',''),str(u.get('year','')),u.get('role','student'),u.get('created_at'),u.get('github'),u.get('linkedin'),u.get('instagram')))
            member_rows += [(email,cid) for cid in u.get('enrolled_clubs',[])]
            registration_rows += [(email,eid) for eid in u.get('enrolled_events',[])]
        _sync_rows(conn,'users',['email','name','col_id','password_hash','skill','intrest','branch','year','role','created_at','github','linkedin','instagram'],user_rows,'email')
        _replace_rows(conn,'club_memberships',['user_email','club_id'],member_rows)
        _replace_rows(conn,'event_registrations',['user_email','event_id'],registration_rows)
        conn.commit(); cur.close()
    except Exception: conn.rollback(); raise
    finally: conn.close()

def load_clubs():
    conn=get_connection(); cur=conn.cursor(dictionary=True)
    try:
        clubs={}
        for r in _rows(cur,"SELECT * FROM clubs"):
            cid=r.pop('club_id'); clubs[cid]=r
            clubs[cid]['pending_members']=[]; clubs[cid]['achievements']=[]
        for r in _rows(cur,"SELECT club_id,user_email FROM club_join_requests"):
            if r['club_id'] in clubs: clubs[r['club_id']]['pending_members'].append(r['user_email'])
        for r in _rows(cur,"SELECT * FROM club_achievements ORDER BY achievement_id"):
            if r['club_id'] in clubs: clubs[r['club_id']]['achievements'].append({'title':r['title'],'description':r['description'],'icon':r['icon']})
        for r in _rows(cur,"SELECT * FROM club_advisors"):
            if r['club_id'] in clubs: clubs[r['club_id']]['faculty_advisor']={'name':r['name'],'email':r['email'],'department':r['department'],'temporary_token':r['temporary_token'] or ''}
        return clubs
    finally: cur.close(); conn.close()

def save_clubs(clubs):
    conn=get_connection()
    try:
        cur=conn.cursor(); rows=[]; requests=[]; achievements=[]; advisors=[]
        for cid,c in clubs.items():
            rows.append((cid,c.get('name',''),c.get('category',''),c.get('manager_email'),c.get('status','active'),c.get('logo'),c.get('about',''),c.get('instagram',''),c.get('president_email'),c.get('president_name')))
            requests += [(cid,e) for e in c.get('pending_members',[])]
            achievements += [(cid,a.get('title',''),a.get('description',''),a.get('icon','fa-trophy')) for a in c.get('achievements',[])]
            a=c.get('faculty_advisor')
            if a: advisors.append((cid,a.get('name',''),a.get('email',''),a.get('department',''),a.get('temporary_token','')))
        cur.execute('DELETE FROM club_join_requests')
        cur.execute('DELETE FROM club_achievements')
        cur.execute('DELETE FROM club_advisors')
        _sync_rows(conn,'clubs',['club_id','name','category','manager_email','status','logo','about','instagram','president_email','president_name'],rows,'club_id')
        if requests: cur.executemany('INSERT INTO club_join_requests (club_id,user_email) VALUES (%s,%s)',requests)
        if achievements: cur.executemany('INSERT INTO club_achievements (club_id,title,description,icon) VALUES (%s,%s,%s,%s)',achievements)
        if advisors: cur.executemany('INSERT INTO club_advisors (club_id,name,email,department,temporary_token) VALUES (%s,%s,%s,%s,%s)',advisors)
        conn.commit(); cur.close()
    except Exception: conn.rollback(); raise
    finally: conn.close()

def load_events():
    conn=get_connection(); cur=conn.cursor(dictionary=True)
    try:
        events={}
        for r in _rows(cur,'SELECT * FROM events'):
            eid=r.pop('event_id'); r['date']=str(r.pop('event_date')) if r.get('event_date') is not None else ''; events[eid]=r; events[eid]['pending_participants']=[]
        for r in _rows(cur,'SELECT event_id,user_email FROM event_join_requests'):
            if r['event_id'] in events: events[r['event_id']]['pending_participants'].append(r['user_email'])
        return events
    finally: cur.close(); conn.close()

def save_events(events):
    conn=get_connection()
    try:
        cur=conn.cursor(); rows=[]; pending=[]
        for eid,e in events.items():
            rows.append((eid,e.get('club_id'),e.get('title',''),e.get('date'),e.get('location',''),e.get('registration_deadline'),e.get('description',''),e.get('category',''),int(bool(e.get('is_recruitment',False))),e.get('status',''),e.get('thumbnail',''),e.get('google_form_link','')))
            pending += [(eid,email) for email in e.get('pending_participants',[])]
        _replace_rows(conn,'event_join_requests',['event_id','user_email'],pending)
        _sync_rows(conn,'events',['event_id','club_id','title','event_date','location','registration_deadline','description','category','is_recruitment','status','thumbnail','google_form_link'],rows,'event_id')
        conn.commit(); cur.close()
    except Exception: conn.rollback(); raise
    finally: conn.close()

def load_messages(table, key_column, key):
    conn=get_connection(); cur=conn.cursor(dictionary=True)
    try:
        cur.execute(f'SELECT sender_name,message_text,message_time FROM {table} WHERE {key_column}=%s ORDER BY message_id',(key,))
        return [{'sender':r['sender_name'],'message':r['message_text'],'time':str(r['message_time'])} for r in cur.fetchall()]
    finally: cur.close(); conn.close()

def append_message(table,key_column,key,sender,message,time_str):
    conn=get_connection()
    try:
        cur=conn.cursor()
        cur.execute(f'INSERT INTO {table} ({key_column},sender_name,message_text,message_time) VALUES (%s,%s,%s,%s)',(key,sender,message,time_str))
        conn.commit(); cur.close(); return True
    except Exception: conn.rollback(); raise
    finally: conn.close()

class userdata:
    def __init__(self,file_name=None): self.file_name=file_name
    def load_user(self): return load_users()
    def valid_user(self,email,password):
        user=self.load_user().get(email)
        if not user: return None
        stored=user.get('password_hash','')
        return user if stored == password else None
    def user_register(self,name,id,email,password,intrest,skill,branch,year):
        users=self.load_user()
        if email in users: return False
        users[email]={'name':(name or 'User').strip(),'col_id':id,'password_hash':password,'skill':skill,'intrest':intrest,'branch':branch,'year':year,'role':'student','created_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'enrolled_clubs':[],'enrolled_events':[]}
        save_users(users); return True
    def user_to_admin(self,email):
        users=self.load_user()
        if email not in users: return False
        users[email]['role']='admin'; save_users(users); return True
    def update_role(self,email,new_role):
        users=self.load_user()
        if email not in users: return False
        users[email]['role']=new_role; save_users(users); return True
    def update_student(self,email,name,branch,skills=None,interests=None,github=None,linkedin=None,instagram=None):
        users=self.load_user()
        if email not in users: return False
        u=users[email]; u['name']=(name or u.get('name','User')).strip(); u['branch']=branch
        if skills is not None: u['skill']=skills
        if interests is not None: u['intrest']=interests
        if github is not None: u['github']=github.strip()
        if linkedin is not None: u['linkedin']=linkedin.strip()
        if instagram is not None: u['instagram']=instagram.strip()
        save_users(users); return True
    def register_for_event(self,email,event_id):
        users=self.load_user()
        if email not in users or event_id in users[email].setdefault('enrolled_events',[]): return False
        users[email]['enrolled_events'].append(event_id); save_users(users); return True
    def get_all_users(self): return self.load_user()
    def delete_user(self,email):
        users=self.load_user()
        if email not in users: return False
        del users[email]; save_users(users); return True
    def join_club(self,email,club_id):
        users=self.load_user()
        if email not in users: return False
        if club_id not in users[email].setdefault('enrolled_clubs',[]): users[email]['enrolled_clubs'].append(club_id); save_users(users)
        return True
    def remove_club(self,email,club_id):
        users=self.load_user()
        if email not in users: return False
        if club_id in users[email].setdefault('enrolled_clubs',[]): users[email]['enrolled_clubs'].remove(club_id); save_users(users)
        return True
    def get_club_members(self,club_id):
        return [{'email':e,'name':u.get('name','Unknown'),'branch':u.get('branch','N/A'),'year':u.get('year','N/A')} for e,u in self.load_user().items() if club_id in u.get('enrolled_clubs',[])]
    def get_event_members(self,event_id):
        return [{'email':e,'name':u.get('name','Unknown'),'branch':u.get('branch','N/A'),'year':u.get('year','N/A')} for e,u in self.load_user().items() if event_id in u.get('enrolled_events',[])]

db=userdata()
if os.getenv("BOOTSTRAP_ADMIN_EMAIL"):
    db.user_to_admin(os.getenv("BOOTSTRAP_ADMIN_EMAIL"))

class club:
    def __init__(self,file=None): self.file_name=file
    def load_club(self): return load_clubs()
    def new_club(self,name,category,manager_email):
        clubs=self.load_club(); n=max([int(k[2:]) for k in clubs if k.startswith('#C') and k[2:].isdigit()] or [0])+1
        clubs[f'#C{n:03d}']={'name':name,'category':category,'manager_email':manager_email,'status':'active','pending_members':[],'achievements':[]}; save_clubs(clubs); return True
    def request_join(self,club_id,email):
        c=self.load_club()
        if club_id not in c: return False
        c[club_id].setdefault('pending_members',[])
        if email not in c[club_id]['pending_members']: c[club_id]['pending_members'].append(email); save_clubs(c)
        return True
    def remove_request(self,club_id,email):
        c=self.load_club()
        if club_id in c and email in c[club_id].get('pending_members',[]): c[club_id]['pending_members'].remove(email); save_clubs(c); return True
        return False
    def delete_club(self,club_id):
        c=self.load_club()
        if club_id not in c: return False
        del c[club_id]; save_clubs(c)
        users=db.load_user()
        for u in users.values(): u['enrolled_clubs']=[x for x in u.get('enrolled_clubs',[]) if x!=club_id]
        save_users(users); return True
    def update_club(self,club_id,name,category):
        c=self.load_club()
        if club_id not in c: return False
        c[club_id].update(name=name,category=category); save_clubs(c); return True
    def update_club_logo(self,club_id,logo_filename):
        c=self.load_club()
        if club_id not in c: return False
        c[club_id]['logo']=logo_filename; save_clubs(c); return True
    def add_achievement(self,club_id,title,description,icon='fa-trophy'):
        c=self.load_club()
        if club_id not in c: return False
        c[club_id].setdefault('achievements',[]).append({'title':title,'description':description,'icon':icon}); save_clubs(c); return True
    def delete_achievement(self,club_id,index):
        c=self.load_club()
        if club_id not in c or not 0<=index<len(c[club_id].get('achievements',[])): return False
        c[club_id]['achievements'].pop(index); save_clubs(c); return True
    def update_club_details(self,club_id,about,instagram):
        c=self.load_club()
        if club_id not in c: return False
        c[club_id]['about']=(about or '').strip(); c[club_id]['instagram']=(instagram or '').strip(); save_clubs(c); return True
    def assign_president(self,club_id,president_email,president_name):
        c=self.load_club(); users=db.load_user()
        if club_id not in c: return False,'Club not found'
        if president_email not in users: return False,'No registered user found with that email'
        old=c[club_id].get('president_email')
        if old in users: users[old]['role']='student'
        c[club_id]['president_email']=president_email; c[club_id]['president_name']=(president_name or users[president_email].get('name','President')).strip()
        users[president_email]['role']='manager'; save_users(users); save_clubs(c); return True,'President assigned'
    def remove_president(self,club_id):
        c=self.load_club()
        if club_id not in c: return False
        old=c[club_id].pop('president_email',None); c[club_id].pop('president_name',None)
        if old:
            users=db.load_user()
            if old in users: users[old]['role']='student'; save_users(users)
        save_clubs(c); return True
    def assign_advisor(self,club_id,name,email,department):
        c=self.load_club()
        if club_id not in c: return False
        c[club_id]['faculty_advisor']={'name':name.strip(),'email':email.strip().lower(),'department':department.strip(),'temporary_token':''}; save_clubs(c); return True
    def set_advisor_token(self,club_id,token):
        c=self.load_club()
        if club_id not in c or 'faculty_advisor' not in c[club_id]: return False
        c[club_id]['faculty_advisor']['temporary_token']=token; save_clubs(c); return True
    def find_club_by_advisor_email(self,email):
        for cid,data in self.load_club().items():
            if data.get('faculty_advisor',{}).get('email','').lower()==email.strip().lower(): return cid,data
        return None,None
    def find_club_by_token(self,token):
        for cid,data in self.load_club().items():
            if token and data.get('faculty_advisor',{}).get('temporary_token','')==token: return cid,data
        return None,None

cl=club()

class club_event:
    def __init__(self,file=None): self.filename=file
    def event_load(self): return load_events()
    def new_event(self,my_club_id,title,date,location,deadline,description,category,is_recruitment,status,saved_image,google_form_link=''):
        events=self.event_load(); n=max([int(k[2:]) for k in events if k.startswith('#E') and k[2:].isdigit()] or [0])+1
        events[f'#E{n:03d}']={'club_id':my_club_id,'title':title,'date':date,'location':location,'registration_deadline':deadline,'description':description,'category':category,'is_recruitment':is_recruitment,'status':status,'thumbnail':saved_image,'google_form_link':google_form_link,'pending_participants':[]}; save_events(events); return True
    def request_join(self,event_id,email):
        e=self.event_load()
        if event_id not in e: return False
        e[event_id].setdefault('pending_participants',[])
        if email not in e[event_id]['pending_participants']: e[event_id]['pending_participants'].append(email); save_events(e)
        return True
    def remove_request(self,event_id,email):
        e=self.event_load()
        if event_id in e and email in e[event_id].get('pending_participants',[]): e[event_id]['pending_participants'].remove(email); save_events(e); return True
        return False
    def delete_event(self,event_id):
        e=self.event_load()
        if event_id not in e: return False
        del e[event_id]; save_events(e)
        users=db.load_user()
        for u in users.values(): u['enrolled_events']=[x for x in u.get('enrolled_events',[]) if x!=event_id]
        save_users(users); return True
    def update_event(self,event_id,title,date,location,deadline,description,category,status,google_form_link=''):
        e=self.event_load()
        if event_id not in e: return False
        e[event_id].update(title=title,date=date,location=location,registration_deadline=deadline,description=description,category=category,status=status,google_form_link=google_form_link); save_events(e); return True

eve=club_event()

class ClubChat:
    def __init__(self,file=None): pass
    def load_chat(self):
        conn=get_connection(); cur=conn.cursor()
        try:
            ids=[r[0] for r in _rows(cur,'SELECT club_id FROM clubs')]
            return {cid:load_messages('club_messages','club_id',cid) for cid in ids}
        finally: cur.close(); conn.close()
    def save_message(self,club_id,sender_name,message,time_str): return append_message('club_messages','club_id',club_id,sender_name,message,time_str)
chat_db=ClubChat()

class EventChat:
    def __init__(self,file=None): pass
    def load_chat(self):
        conn=get_connection(); cur=conn.cursor()
        try:
            ids=[r[0] for r in _rows(cur,'SELECT event_id FROM events')]
            return {eid:load_messages('event_messages','event_id',eid) for eid in ids}
        finally: cur.close(); conn.close()
    def save_message(self,event_id,sender_name,message,time_str): return append_message('event_messages','event_id',event_id,sender_name,message,time_str)
event_chat_db=EventChat()

@app.route("/")
def home():
    all_events = eve.event_load()
    all_clubs = cl.load_club()
    # Only show Published events on the home page
    published_events = {eid: e for eid, e in all_events.items() if e.get("status", "Published") == "Published"}
    return render_template("home.html", events=published_events, clubs=all_clubs)

@app.route("/login")
def login():
    if session.get("user_data"):
        role = session.get("user_role", "student")
        next_url = request.args.get("next", "")
        if role == "student":
            if next_url:
                return redirect(next_url)
            return redirect(url_for("std_dashboard"))
        elif role == "manager":
            return redirect(url_for("manager"))
        elif role == "admin":
            return redirect(url_for("admin"))
    next_url = request.args.get("next", "")
    return render_template("login.html", next_url=next_url)
@app.route("/submit",methods=["POST"])
def submit():
    Email=request.form.get("Email")
    Password=request.form.get("Password")
    next_url=request.form.get("next_url", "")
    user_id=db.valid_user(Email,Password)
    if user_id:
        session['user_data']=Email
        session['user_role']=user_id.get("role","student")
        if session['user_role']=="student":
            # If there's a next URL (Google Form), open it then land on profile
            if next_url:
                return redirect(next_url)
            return redirect(url_for("std_dashboard"))
        elif session['user_role']=="manager":
            return redirect(url_for('manager'))
        elif session['user_role']=="admin":
            return redirect(url_for('admin'))
         
    else:
        return render_template("login.html", error="Invalid credentials, please try again.", next_url=next_url)

@app.route("/google_login", methods=["POST"])
def google_login():
    email = request.form.get("email")
    name = request.form.get("name", "Google User")
    if not email:
        return redirect(url_for("login"))
        
    all_users = db.load_user()
    if email in all_users:
        session['user_data'] = email
        session['user_role'] = all_users[email].get("role", "student")
    else:
        # Auto-register google user
        name = name.strip() if name else "Google User"
        db.user_register(name, "Google_OAuth", email, "oauth123", [], [], "N/A", "N/A")
        session['user_data'] = email
        session['user_role'] = "student"
        
    role = session['user_role']
    if role == "student":
        return redirect(url_for("std_dashboard"))
    elif role == "manager":
        return redirect(url_for("manager"))
    else:
        return redirect(url_for("admin"))

@app.route("/register")
def reg():
    return render_template("register.html")    
@app.route("/new_user",methods=["POST"])
def register():
    std_name=request.form.get('student_name')
    std_id=request.form.get('student_col_id')
    std_email=request.form.get('student_col_email')
    std_branch=request.form.get('student_branch')
    std_year=request.form.get('student_year')
    temp_pas=request.form.get('temp_password')
    std_password=request.form.get('conform_password')
    std_intrest=request.form.getlist("interests")
    std_skill=request.form.get("skills","")
    if not std_email.lower().endswith("@mitsgwl.ac.in"):
        return render_template("register.html",error="Please use your official @mitsgwl.ac.in email.")
    if std_skill:
        std_skill_list=[s.strip() for s in std_skill.split(",") if s.strip()]
    else:
        std_skill_list=[]

    if temp_pas == std_password:
        db.user_register(std_name, std_id, std_email, std_password, std_intrest, std_skill_list, std_branch, std_year)
        return redirect(url_for("login"))
    else:
        return render_template('register.html',error="Passwords do not match!",student_name=std_name,student_col_id=std_id,student_col_email=std_email,student_branch=std_branch,student_year=std_year)
@app.route("/student")
def std_dashboard():
    email=session.get('user_data')
    if not email:
        return redirect(url_for("login"))
    all_user=db.load_user()
    current_std=all_user.get(email)
    
    all_events = eve.event_load()
    all_clubs = cl.load_club()

    # Only show clubs the student is a member of
    enrolled_club_ids = current_std.get("enrolled_clubs", []) if current_std else []
    my_clubs = {cid: all_clubs[cid] for cid in enrolled_club_ids if cid in all_clubs}

    return render_template("index.html", student=current_std, events=all_events, clubs=all_clubs, my_clubs=my_clubs, student_email=email)
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/register_event", methods=["POST"])
def register_event():
    email = session.get('user_data')
    if not email:
        return {"status": "error", "message": "Unauthorized"}, 401

    data = request.get_json()
    if not data or "event_id" not in data:
        return {"status": "error", "message": "Missing event ID"}, 400
    
    event_id = data["event_id"]
    success = eve.request_join(event_id, email)
    if success:
        all_events = eve.event_load()
        event_info = all_events.get(event_id, {})
        redirect_url = event_info.get("google_form_link", "")
        return {"status": "success", "message": "Join request sent to manager for approval.", "redirect_url": redirect_url, "google_form": redirect_url}, 200
    else:
        return {"status": "error", "message": "Failed to send request."}, 500

@app.route("/api/chat/send", methods=["POST"])
def send_chat():
    data = request.get_json()
    club_id = data.get("club_id")
    sender = data.get("sender", "Unknown")
    message = data.get("message")
    time_str = data.get("time")
    if club_id and message:
        chat_db.save_message(club_id, sender, message, time_str)
        return {"status": "success"}, 200
    return {"status": "error"}, 400

@app.route("/api/chat/get")
def get_chat():
    club_id = request.args.get("club_id", "")
    chats = chat_db.load_chat()
    return {"messages": chats.get(club_id, [])}, 200

@app.route("/api/club_profile")
def api_club_profile():
    """Return full club profile data for the student-facing club modal."""
    club_id = request.args.get("club_id", "")
    all_clubs = cl.load_club()
    club_data = all_clubs.get(club_id)
    if not club_data:
        return {"error": "Club not found"}, 404

    email = session.get("user_data")
    all_users = db.load_user() if email else {}
    student = all_users.get(email, {}) if email else {}

    is_member = club_id in student.get("enrolled_clubs", [])
    is_pending = email in club_data.get("pending_members", []) if email else False

    return {
        "name": club_data.get("name", ""),
        "category": club_data.get("category", ""),
        "about": club_data.get("about", ""),
        "instagram": club_data.get("instagram", ""),
        "manager_email": club_data.get("manager_email", ""),
        "president_email": club_data.get("president_email", ""),
        "president_name": club_data.get("president_name", ""),
        "achievements": club_data.get("achievements", []),
        "is_member": is_member,
        "is_pending": is_pending,
    }, 200

@app.route("/api/student_profile")
def api_student_profile():
    if session.get("user_role") != "manager":
        return {"error": "Unauthorized"}, 401
    email = request.args.get("email")
    if not email:
        return {"error": "Missing email"}, 400
    all_users = db.load_user()
    user = all_users.get(email)
    if not user:
        return {"error": "User not found"}, 404
        
    return {
        "name": user.get("name", ""),
        "email": email,
        "branch": user.get("branch", ""),
        "year": user.get("year", ""),
        "skill": user.get("skill", []),
        "intrest": user.get("intrest", []),
        "github": user.get("github", ""),
        "linkedin": user.get("linkedin", ""),
        "instagram": user.get("instagram", ""),
    }, 200

@app.route("/api/event_chat/send", methods=["POST"])
def send_event_chat():
    data = request.get_json()
    event_id = data.get("event_id")
    sender = data.get("sender", "Unknown")
    message = data.get("message")
    time_str = data.get("time")
    if event_id and message:
        event_chat_db.save_message(event_id, sender, message, time_str)
        return {"status": "success"}, 200
    return {"status": "error"}, 400

@app.route("/api/event_chat/get")
def get_event_chat():
    event_id = request.args.get("event_id", "")
    chats = event_chat_db.load_chat()
    return {"messages": chats.get(event_id, [])}, 200

@app.route("/event/<event_id>")
def event_detail(event_id):
    all_events = eve.event_load()
    if event_id not in all_events:
        return "Event not found", 404
    event = all_events[event_id]
    all_clubs = cl.load_club()
    club = all_clubs.get(event.get("club_id"), {})
    # Pass the logged-in student so the template can check enrollment status
    student = None
    email = session.get('user_data')
    if email:
        student = db.load_user().get(email)
    return render_template("event_detail.html", event=event, club=club, event_id=event_id, student=student)

@app.route("/student/edit_profile", methods=["POST"])
def edit_profile():
    email = session.get('user_data')
    if not email:
        return redirect(url_for("login"))
    name = request.form.get("name")
    branch = request.form.get("branch")
    skills_raw = request.form.get("skills", "")
    interests_raw = request.form.get("interests", "")
    github = request.form.get("github")
    linkedin = request.form.get("linkedin")
    instagram = request.form.get("instagram", "")
    
    skills_list = [s.strip() for s in skills_raw.split(",") if s.strip()] if skills_raw else None
    interests_list = [s.strip() for s in interests_raw.split(",") if s.strip()] if interests_raw else None
    if name and branch and github and linkedin:
        db.update_student(email, name, branch, skills=skills_list, interests=interests_list, github=github, linkedin=linkedin, instagram=instagram)
    return redirect(url_for("std_dashboard"))

@app.route("/manager")
def manager():
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
    
    all_user = db.load_user()
    manager_info = all_user.get(email)
    
    all_club = cl.load_club()
    my_club = None
    my_cid = None
    for cid, club_info in all_club.items():
        # Grant access to the club's manager OR the assigned president
        if club_info.get("manager_email") == email or club_info.get("president_email") == email:
            my_cid = cid
            my_club = club_info
            break
    # Pass whether current user is the original club manager (to show/hide president controls)
    is_club_owner = (my_club is not None and my_club.get("manager_email") == email)
            
    all_events = eve.event_load()
    my_events = {}
    if my_cid:
        my_events = {eid: ev for eid, ev in all_events.items() if ev.get("club_id") == my_cid}
    
    first_eid = list(my_events.keys())[0] if my_events else None

    # Count registrations per event and collect participants
    all_users_data = db.load_user()
    reg_counts = {}
    event_participants = {}
    pending_event_members = {} # To collect pending members
    
    for eid in my_events:
        reg_counts[eid] = 0
        event_participants[eid] = db.get_event_members(eid)
        reg_counts[eid] = len(event_participants[eid])
        pending_event_members[eid] = []
        
        # Pending participants
        ev_data = all_events.get(eid, {})
        for pen_email in ev_data.get("pending_participants", []):
            if pen_email in all_users_data:
                u = all_users_data[pen_email]
                pending_event_members[eid].append({
                    "email": pen_email,
                    "name": u.get("name", "Unknown"),
                    "branch": u.get("branch", "N/A"),
                    "year": u.get("year", "N/A")
                })

    # Current members of the manager's club
    club_members = db.get_club_members(my_cid) if my_cid else []
    
    # Pending members of the manager's club
    pending_club_members = []
    if my_club:
        for pen_email in my_club.get("pending_members", []):
            if pen_email in all_users_data:
                u = all_users_data[pen_email]
                pending_club_members.append({
                    "email": pen_email,
                    "name": u.get("name", "Unknown"),
                    "branch": u.get("branch", "N/A"),
                    "year": u.get("year", "N/A")
                })

    return render_template("manager.html", club=my_club, events=my_events, manager=manager_info,
        my_cid=my_cid, reg_counts=reg_counts, club_members=club_members,
        event_participants=event_participants, pending_club_members=pending_club_members,
        pending_event_members=pending_event_members,
        is_club_owner=is_club_owner, manager_email=email)

@app.route("/manager/edit_club", methods=["POST"])
def edit_club():
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
        
    club_id = request.form.get("club_id")
    name = request.form.get("club_name")
    category = request.form.get("category")
    if club_id and name and category:
        cl.update_club(club_id, name, category)
    return redirect(url_for("manager"))

@app.route("/manager/update_club_logo", methods=["POST"])
def update_club_logo():
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
    club_id = request.form.get("club_id")
    logo = request.files.get("club_logo")
    if club_id and logo and logo.filename != '':
        filename = secure_filename(logo.filename)
        upload_dir = os.path.join("static", "uploads", "clubs")
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)
        logo.save(filepath)
        cl.update_club_logo(club_id, filename)
    return redirect(url_for("manager"))

@app.route("/manager/add_achievement", methods=["POST"])
def add_achievement():
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
    club_id = request.form.get("club_id")
    title = request.form.get("title")
    description = request.form.get("description")
    icon = request.form.get("icon", "fa-trophy")
    if club_id and title and description:
        cl.add_achievement(club_id, title, description, icon)
    return redirect(url_for("manager"))

@app.route("/manager/delete_achievement", methods=["POST"])
def delete_achievement():
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
    club_id = request.form.get("club_id")
    index = request.form.get("index")
    if club_id and index is not None:
        try:
            cl.delete_achievement(club_id, int(index))
        except ValueError:
            pass
    return redirect(url_for("manager"))

@app.route("/manager/update_club_details", methods=["POST"])
def update_club_details():
    """Save club About description and Instagram link."""
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
    club_id = request.form.get("club_id")
    about = request.form.get("about", "")
    instagram = request.form.get("instagram", "")
    if club_id:
        cl.update_club_details(club_id, about, instagram)
    return redirect(url_for("manager"))

@app.route("/manager/assign_president", methods=["POST"])
def assign_president():
    """Assign a club president by Gmail — grants them manager portal access."""
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
    all_club = cl.load_club()
    club_id = request.form.get("club_id")
    # Only the original manager (not president) can assign
    if not club_id or all_club.get(club_id, {}).get("manager_email") != email:
        return redirect(url_for("manager"))
    president_email = request.form.get("president_email", "").strip().lower()
    president_name = request.form.get("president_name", "").strip()
    if president_email and president_name:
        cl.assign_president(club_id, president_email, president_name)
    return redirect(url_for("manager"))

@app.route("/manager/remove_president", methods=["POST"])
def remove_president():
    """Remove the club president and revert their role to student."""
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
    club_id = request.form.get("club_id")
    all_club = cl.load_club()
    # Only original manager can remove president
    if not club_id or all_club.get(club_id, {}).get("manager_email") != email:
        return redirect(url_for("manager"))
    cl.remove_president(club_id)
    return redirect(url_for("manager"))

@app.route("/manager/add_member", methods=["POST"])
def add_member():
    if session.get("user_role") != "manager":
        return {"status": "error", "message": "Unauthorized"}, 401
    member_email = request.form.get("member_email", "").strip()
    club_id = request.form.get("club_id")
    if member_email and club_id:
        success = db.join_club(member_email, club_id)
        if success:
            cl.remove_request(club_id, member_email)
            return {"status": "success"}, 200
        else:
            return {"status": "error", "message": "User not found or invalid email."}, 404
    return {"status": "error", "message": "Missing info"}, 400

@app.route("/manager/remove_member", methods=["POST"])
def remove_member():
    if session.get("user_role") != "manager":
        return {"status": "error", "message": "Unauthorized"}, 401
    member_email = request.form.get("member_email")
    club_id = request.form.get("club_id")
    if member_email and club_id:
        success = db.remove_club(member_email, club_id)
        if success:
            return {"status": "success"}, 200
        else:
            return {"status": "error", "message": "User not found or not in club."}, 404
    return {"status": "error", "message": "Missing info"}, 400

@app.route("/api/join_club", methods=["POST"])
def api_join_club():
    email = session.get("user_data")
    if not email:
        return {"status": "error", "message": "Unauthorized"}, 401
    data = request.get_json()
    club_id = data.get("club_id") if data else None
    if not club_id:
        return {"status": "error", "message": "Missing club_id"}, 400
    success = cl.request_join(club_id, email)
    if success:
        return {"status": "success", "message": "Join request sent to manager."}, 200
    return {"status": "error", "message": "Failed to send request."}, 500

@app.route("/manager/approve_club_member", methods=["POST"])
def approve_club_member():
    if session.get("user_role") != "manager":
        return {"status": "error", "message": "Unauthorized"}, 401
    data = request.get_json()
    club_id = data.get("club_id")
    member_email = data.get("member_email")
    action = data.get("action")
    if club_id and member_email and action:
        cl.remove_request(club_id, member_email)
        if action == "approve":
            db.join_club(member_email, club_id)
        return {"status": "success"}, 200
    return {"status": "error"}, 400

@app.route("/manager/approve_event_member", methods=["POST"])
def approve_event_member():
    if session.get("user_role") != "manager":
        return {"status": "error", "message": "Unauthorized"}, 401
    data = request.get_json()
    event_id = data.get("event_id")
    member_email = data.get("member_email")
    action = data.get("action")
    if event_id and member_email and action:
        eve.remove_request(event_id, member_email)
        if action == "approve":
            db.register_for_event(member_email, event_id)
        return {"status": "success"}, 200
    return {"status": "error"}, 400

@app.route("/api/club_members")
def api_club_members():
    club_id = request.args.get("club_id", "")
    members = db.get_club_members(club_id)
    return {"members": members, "count": len(members)}, 200

@app.route("/api/member_count")
def api_member_count():
    club_id = request.args.get("club_id", "")
    count = len(db.get_club_members(club_id))
    return {"count": count}, 200




@app.route("/manager/delete_event", methods=["POST"])
def delete_event():
    if session.get("user_role") != "manager":
        return redirect(url_for("login"))
    event_id = request.form.get("event_id")
    if event_id:
        eve.delete_event(event_id)
    return redirect(url_for("manager"))

@app.route("/manager/update_event", methods=["POST"])
def update_event():
    if session.get("user_role") != "manager":
        return redirect(url_for("login"))
    event_id = request.form.get("event_id")
    title = request.form.get("event_title")
    category = request.form.get("event_cat")
    date = request.form.get("date")
    location = request.form.get("Location")
    deadline = request.form.get("Deadline")
    description = request.form.get("description")
    google_form_link = request.form.get("google_form_link", "")
    action = request.form.get("action", "Published")
    status = "Draft" if action == "Draft" else "Published"
    
    # If club has an advisor, force Draft until approved
    all_clubs = cl.load_club()
    event_data = eve.event_load().get(event_id, {})
    club_id = event_data.get("club_id")
    if club_id and all_clubs.get(club_id, {}).get("faculty_advisor"):
        status = "Draft"
        
    if event_id:
        eve.update_event(event_id, title, date, location, deadline, description, category, status, google_form_link)
    return redirect(url_for("manager"))

@app.route("/api/event_count")
def event_count():
    event_id = request.args.get("event_id", "")
    all_users_data = db.load_user()
    count = sum(1 for u in all_users_data.values() if event_id in u.get("enrolled_events", []))
    return {"count": count}, 200

@app.route("/admin")
def admin():
    if session.get("user_role")!="admin":
        return redirect(url_for("login"))
    
    all_user=db.load_user()
    all_club=cl.load_club()

    all_student=sum(1 for u in all_user.values() if u.get("role") == "student")
    all_manager=sum(1 for u in all_user.values() if u.get("role") == "manager")
    total_clubs=len(all_club)


    return render_template("super_admin.html",total_club=total_clubs,total_stu=all_student,total_mana=all_manager, users=all_user, clubs=all_club)

@app.route("/admin/creat_club",methods=["POST"])
def creat_club():
    if session.get("user_role")!="admin":
        return redirect(url_for("login"))
    name=request.form.get("clubName")
    category=request.form.get("clubcategory")
    email=request.form.get("email")
    advisor_name = request.form.get("advisor_name", "").strip()
    advisor_email = request.form.get("advisor_email", "").strip()
    advisor_dept = request.form.get("advisor_department", "").strip()

    all_user=db.load_user()
    if email in all_user:
        cl.new_club(name,category,email)
        db.update_role(email,"manager")
        # Assign advisor if all advisor fields provided
        if advisor_name and advisor_email and advisor_dept:
            # Find the newly created club id (highest numbered)
            all_clubs = cl.load_club()
            new_cid = max(all_clubs.keys())
            cl.assign_advisor(new_cid, advisor_name, advisor_email, advisor_dept)
    return redirect(url_for("admin"))
@app.route("/admin/manage_users")
def manage_users():
    if session.get('user_role') != 'admin':
        return redirect(url_for("login"))
    # manage_users is handled by the SPA in super_admin.html
    return redirect(url_for("admin"))

@app.route("/admin/delete_user", methods=["POST"])
def delete_user():
    if session.get("user_role")!="admin":
        return redirect(url_for("login"))
    email = request.form.get("email")
    if email:
        db.delete_user(email)
    return redirect(url_for("admin"))

@app.route("/admin/change_role", methods=["POST"])
def change_role():
    if session.get("user_role")!="admin":
        return redirect(url_for("login"))
    email = request.form.get("email")
    new_role = request.form.get("new_role")
    if email and new_role:
        db.update_role(email, new_role)
    return redirect(url_for("admin"))

@app.route("/admin/delete_club", methods=["POST"])
def delete_club():
    if session.get("user_role")!="admin":
        return redirect(url_for("login"))
    club_id = request.form.get("club_id")
    if club_id:
        cl.delete_club(club_id)
    return redirect(url_for("admin"))

@app.route("/admin/edit_club", methods=["POST"])
def admin_edit_club():
    if session.get("user_role") != "admin":
        return redirect(url_for("login"))
    club_id = request.form.get("club_id")
    name = request.form.get("club_name")
    category = request.form.get("category")
    manager_email = request.form.get("manager_email")
    advisor_name = request.form.get("advisor_name", "").strip()
    advisor_email = request.form.get("advisor_email", "").strip()
    advisor_dept = request.form.get("advisor_department", "").strip()

    if club_id and name and category:
        cl.update_club(club_id, name, category)
        clubs = cl.load_club()
        if club_id in clubs:
            # Check if manager email changed
            old_manager = clubs[club_id].get("manager_email")
            if manager_email and manager_email != old_manager:
                clubs[club_id]["manager_email"] = manager_email
                save_clubs(clubs)
                if manager_email in db.load_user():
                    db.update_role(manager_email, "manager")
            # Update advisor if provided
            if advisor_name and advisor_email and advisor_dept:
                cl.assign_advisor(club_id, advisor_name, advisor_email, advisor_dept)
    return redirect(url_for("admin"))

@app.route("/admin/edit_user", methods=["POST"])
def admin_edit_user():
    if session.get("user_role") != "admin":
        return redirect(url_for("login"))
    email = request.form.get("email")
    name = request.form.get("name")
    branch = request.form.get("branch")
    if email and name and branch:
        db.update_student(email, name, branch)
    return redirect(url_for("admin"))

@app.route("/manager/create_event",methods=["POST"])
def create_event():
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
    
    title = request.form.get("event_title")
    category = request.form.get("event_cat")
    date = request.form.get("date")
    location = request.form.get("Location")
    deadline = request.form.get("Deadline")
    description = request.form.get("description")
    google_form_link = request.form.get("google_form_link", "")
    thumbnail=request.files.get("thumbnail")
    saved_file="default_event.png"

    is_reqruitment=True if request.form.get("reqruitment")== "on" else False
    if thumbnail and thumbnail.filename != '':
        filename = secure_filename(thumbnail.filename)
    
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        thumbnail.save(filepath)
        saved_file = filename
    action=request.form.get("action")
    status= "Draft" if action=="Draft" else "Published"

    all_club=cl.load_club()
    my_cid=None

    for cid,club_info in all_club.items():
        if club_info.get("manager_email")==email:
            my_cid=cid
            break

    if my_cid:
        # If club has an advisor, force Draft until approved
        if all_club.get(my_cid, {}).get("faculty_advisor"):
            status = "Draft"
            
        eve.new_event(my_cid, title, date, location, deadline, description, category, is_reqruitment, status,saved_file,google_form_link)
        return redirect(url_for("manager"))
    else:
        return "Error: No club assigned.", 403


# ─── ADVISOR ROUTES ─────────────────────────────────────────────────────────

@app.route("/advisor-login", methods=["GET", "POST"])
def advisor_login():
    """Passwordless advisor login — email lookup → token → redirect to dashboard."""
    if request.method == "POST":
        email = request.form.get("advisor_email", "").strip().lower()
        club_id, club_data = cl.find_club_by_advisor_email(email)
        if club_id is None:
            return render_template("advisor_login.html",
                                   error="No club found with that advisor email.")
        # Generate a fresh secure token
        token = secrets.token_urlsafe(32)
        cl.set_advisor_token(club_id, token)
        access_url = url_for("advisor_dashboard", token=token, _external=True)
        # DEV shortcut — print URL to terminal instead of sending email
        print("\n" + "=" * 60)
        print(f"[ADVISOR ACCESS LINK for {email}]")
        print(f"  Club : {club_data.get('name')} ({club_id})")
        print(f"  URL  : {access_url}")
        print("=" * 60 + "\n")
        return redirect(access_url)
    return render_template("advisor_login.html")


@app.route("/advisor/dashboard/<token>")
def advisor_dashboard(token):
    """Advisor-facing dashboard — validated by token stored in club.json."""
    club_id, club_data = cl.find_club_by_token(token)
    if club_id is None:
        return render_template("advisor_login.html",
                               error="Invalid or expired access link. Please request a new one."), 403
    # Collect events belonging to this club (all statuses visible to advisor)
    all_events = eve.event_load()
    club_events = {eid: ev for eid, ev in all_events.items()
                   if ev.get("club_id") == club_id}
    advisor = club_data.get("faculty_advisor", {})
    return render_template("advisor_dashboard.html",
                           club=club_data,
                           club_id=club_id,
                           events=club_events,
                           advisor=advisor,
                           token=token)


@app.route("/advisor/review_event", methods=["POST"])
def advisor_review_event():
    """Approve or reject an event. Validated by token passed as a form field."""
    token = request.form.get("token", "")
    event_id = request.form.get("event_id", "")
    action = request.form.get("action", "")  # 'approve' or 'reject'

    # Validate token
    club_id, club_data = cl.find_club_by_token(token)
    if club_id is None:
        return redirect(url_for("advisor_login"))

    events = eve.event_load()
    if event_id in events and events[event_id].get("club_id") == club_id:
        if action == "approve":
            events[event_id]["status"] = "Published"
        elif action == "reject":
            events[event_id]["status"] = "Rejected"
        save_events(events)

    return redirect(url_for("advisor_dashboard", token=token, done='approved' if action == 'approve' else 'rejected'))


@app.route("/advisor/assign_president", methods=["POST"])
def advisor_assign_president():
    """Advisor assigns a club president."""
    token = request.form.get("token", "")
    club_id, club_data = cl.find_club_by_token(token)
    if club_id is None:
        return redirect(url_for("advisor_login"))

    president_email = request.form.get("president_email", "").strip().lower()
    president_name = request.form.get("president_name", "").strip()
    
    if president_email and president_name:
        cl.assign_president(club_id, president_email, president_name)
        
    return redirect(url_for("advisor_dashboard", token=token, done='president_assigned'))


@app.route("/advisor/remove_president", methods=["POST"])
def advisor_remove_president():
    """Advisor removes the club president."""
    token = request.form.get("token", "")
    club_id, club_data = cl.find_club_by_token(token)
    if club_id is None:
        return redirect(url_for("advisor_login"))

    cl.remove_president(club_id)
    return redirect(url_for("advisor_dashboard", token=token, done='president_removed'))


@app.route("/advisor/delete_event", methods=["POST"])
def advisor_delete_event():
    """Advisor deletes an event."""
    token = request.form.get("token", "")
    event_id = request.form.get("event_id", "")
    
    # Validate token
    club_id, club_data = cl.find_club_by_token(token)
    if club_id is None:
        return redirect(url_for("advisor_login"))

    events = eve.event_load()
    if event_id in events and events[event_id].get("club_id") == club_id:
        eve.delete_event(event_id)
        
    return redirect(url_for("advisor_dashboard", token=token, done='event_deleted'))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
