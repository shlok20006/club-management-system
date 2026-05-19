from flask import Flask,render_template,request,Response,redirect,url_for,session
import json

app=Flask(__name__)
app.secret_key="Mits_club_student"
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads/events'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

class userdata():
    def __init__(self,file_name):
        self.file_name=file_name
    def load_user(self):
        with open(self.file_name,'r') as f:
            return json.load(f)
    def valid_user(self,email,password):
        user=self.load_user()
        if email in user and user[email]["password"]==password:
            return user[email]
        else:
            return None
    def user_register(self,name,id,email,password,intrest,skill,branch,year):
        try:
            user=self.load_user()
        except ( FileNotFoundError,json.JSONDecodeError):
            user={}
        user[email]={
            "name":name,
            "col_id":id,
            "password":password,
            "skill":skill,
            "intrest":intrest,
            "branch":branch,
            "year":year,
            "role":"student",
        }    
        with open('user.json','w')as f:
            json.dump(user,f,indent=4)
        return True
    def user_to_admin(self,email):
        user=self.load_user()
        if email in user:
            user[email]["role"]="admin"
            with open("user.json",'w')as f:
                json.dump(user,f,indent=4)
            return True
        return False
    def update_role(self,email,new_role):
        user=self.load_user()
        if email in user:
            user[email]["role"]=new_role
            with open(self.file_name, 'w') as f:
                json.dump(user, f, indent=4)
            return True
        return False


db=userdata("user.json")
db.user_to_admin("25ad1ad08@mitsgwl.ac.in")


class club():
    def __init__(self,file="club.json"):
        self.file_name=file

    def load_club(self):
        try:
            with open(self.file_name,'r')as f:
                return json.load(f)
        except (FileNotFoundError,json.JSONDecodeError):
            return{}
    def new_club(self,name,category,manager_email):
        clubs=self.load_club()

        club_id=f"#C{len(clubs) +1:03d}"
        clubs[club_id]={
            "name":name,
            "category":category,
            "manager_email":manager_email,
            "status":"active",
        }
        with open("club.json",'w')as f:
            json.dump(clubs,f,indent=4)
        return True

cl=club()

class club_event():
    def __init__(self,file="event.json"):
        self.filename=file
    def event_load(self):
        try:
            with open(self.filename, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        
    def new_event(self,my_club_id, title, date, location, deadline, description, category, is_recruitment, status,saved_image):
        events = self.event_load()
        event_id = f"#E{len(events) + 1:03d}" 
        
        events[event_id] = {
            "club_id": my_club_id,
            "title": title,
            "date": date,
            "location": location,
            "registration_deadline": deadline,
            "description": description,
            "category": category,
            "is_recruitment": is_recruitment,
            "status": status, 
            "thumbnail": saved_image, 
        }    
        with open(self.filename, 'w') as f:
            json.dump(events, f, indent=4)
        return True


eve=club_event()  
        


@app.route("/")
def home():
    return render_template("home.html")

@app.route("/login")
def login():
    return render_template("login.html")
@app.route("/submit",methods=["POST"])
def submit():
    Email=request.form.get("Email")
    Password=request.form.get("Password")
    user_id=db.valid_user(Email,Password)
    if user_id:
        session['user_data']=Email
        session['user_role']=user_id.get("role","student")
        if session['user_role']=="student":
            return redirect(url_for("std_dashboard"))
        elif session['user_role']=="manager":
            return redirect(url_for('manager'))
        elif session['user_role']=="admin":
            return redirect(url_for('admin'))
         
    else:
        return render_template("login.html",error="Invalid credentials, please try again.")
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

    return render_template("index.html",student=current_std)    
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/manager")
def manager():
    email = session.get("user_data")
    if not email or session.get("user_role") != "manager":
        return redirect(url_for("login"))
    
    all_club = cl.load_club()
    my_club = None
    my_cid = None
    for cid, club_info in all_club.items():
        if club_info.get("manager_email") == email:
            my_cid = cid
            my_club = club_info
            break
            
    all_events = eve.event_load()
    my_events = {}
    if my_cid:
        my_events = {eid: ev for eid, ev in all_events.items() if ev.get("club_id") == my_cid}

    return render_template("manager.html", club=my_club, events=my_events)



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

    all_user=db.load_user()
    if email in all_user:
        cl.new_club(name,category,email)

        db.update_role(email,"manager")
    else:
        pass
    return redirect(url_for("admin"))
@app.route("/admin/manage_users")
def manage_users():
    if session.get('user_role') != 'admin':
        return redirect(url_for("login"))
        
    all_users = db.get_all_users()
    return render_template("manage_users.html", users=all_users)

@app.route("/manager/create_event",methods=["POST"])
def create_event():
    email=session["user_data"]
    if session.get("user_role") != "manager":
        return redirect(url_for("login"))
    
    title = request.form.get("event_title")
    category = request.form.get("event_cat")
    date = request.form.get("date")
    location = request.form.get("Location")
    deadline = request.form.get("Deadline")
    description = request.form.get("description")
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
        eve.new_event(my_cid, title, date, location, deadline, description, category, is_reqruitment, status,saved_file)
        return redirect(url_for("manager"))
    else:
        return "Error: No club assigned.", 403


    


        
