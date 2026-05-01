from flask import Flask,request,render_template
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager,create_access_token,jwt_required,get_jwt_identity,get_jwt
from flask_cors import CORS
from datetime import datetime,timedelta
import bcrypt,os

app=Flask(__name__)

db_url=os.getenv('DATABASE_URL')
if db_url:
    db_url=db_url.replace("mysql://","mysql+pymysql://")
    app.config['SQLALCHEMY_DATABASE_URI']=db_url
else:
    app.config['SQLALCHEMY_DATABASE_URI']='mysql+pymysql://root:YOURPASSWORD@localhost/taskdb'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
app.config['JWT_SECRET_KEY']='supersecretkey_supersecretkey_12345'
app.config['JWT_ACCESS_TOKEN_EXPIRES']=timedelta(hours=2)

db=SQLAlchemy(app)
jwt=JWTManager(app)
CORS(app)

class User(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(100))
    email=db.Column(db.String(100),unique=True)
    password=db.Column(db.String(200))
    role=db.Column(db.String(20))

class Project(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(100))
    description=db.Column(db.String(200))
    created_by=db.Column(db.Integer,db.ForeignKey('user.id'))

class Task(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    title=db.Column(db.String(100))
    description=db.Column(db.String(200))
    status=db.Column(db.String(20),default="ToDo")
    due_date=db.Column(db.DateTime)
    assigned_to=db.Column(db.Integer,db.ForeignKey('user.id'))
    project_id=db.Column(db.Integer,db.ForeignKey('project.id'))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/create_tables')
def create_tables():
    db.create_all()
    return {"message":"Tables created"}

@app.route('/signup',methods=['POST'])
def signup():
    data=request.json
    if not data or not all(k in data for k in ['name','email','password','role']):
        return {"message":"Missing fields"},400
    if data['role'] not in ['Admin','Member']:
        return {"message":"Invalid role"},400
    if User.query.filter_by(email=data['email']).first():
        return {"message":"Email exists"},400
    hashed=bcrypt.hashpw(data['password'].encode(),bcrypt.gensalt()).decode()
    user=User(name=data['name'],email=data['email'],password=hashed,role=data['role'])
    db.session.add(user)
    db.session.commit()
    return {"message":"User created"}

@app.route('/login',methods=['POST'])
def login():
    data=request.json
    user=User.query.filter_by(email=data['email']).first()
    if not user:
        return {"message":"Invalid credentials"},401
    if not bcrypt.checkpw(data['password'].encode(),user.password.encode()):
        return {"message":"Invalid credentials"},401
    token=create_access_token(identity=str(user.id),additional_claims={"role":user.role})
    return {"token":token}

@app.route('/create_project',methods=['POST'])
@jwt_required()
def create_project():
    role=get_jwt().get("role")
    user_id=get_jwt_identity()
    if role!='Admin':
        return {"message":"Only Admin"},403
    data=request.json
    if not data or not all(k in data for k in ['name','description']):
        return {"message":"Missing fields"},400
    project=Project(name=data['name'],description=data['description'],created_by=user_id)
    db.session.add(project)
    db.session.commit()
    return {"message":"Project created"}

@app.route('/projects',methods=['GET'])
@jwt_required()
def projects():
    data=Project.query.all()
    return [{"id":p.id,"name":p.name,"description":p.description} for p in data]

@app.route('/create_task',methods=['POST'])
@jwt_required()
def create_task():
    role=get_jwt().get("role")
    if role!='Admin':
        return {"message":"Only Admin"},403
    data=request.json
    if not data or not all(k in data for k in ['title','description','due_date','project_id']):
        return {"message":"Missing fields"},400
    project=db.session.get(Project,data['project_id'])
    if not project:
        return {"message":"Project not found"},400
    task=Task(title=data['title'],description=data['description'],due_date=datetime.strptime(data['due_date'],"%Y-%m-%d"),project_id=data['project_id'])
    db.session.add(task)
    db.session.commit()
    return {"message":"Task created"}

@app.route('/assign_task',methods=['POST'])
@jwt_required()
def assign_task():
    role=get_jwt().get("role")
    if role!='Admin':
        return {"message":"Only Admin"},403
    data=request.json
    task=db.session.get(Task,data['task_id'])
    user=db.session.get(User,data['user_id'])
    if not task:
        return {"message":"Task not found"},404
    if not user:
        return {"message":"User not found"},404
    task.assigned_to=user.id
    db.session.commit()
    return {"message":"Assigned"}

@app.route('/update_task_status',methods=['PUT'])
@jwt_required()
def update_status():
    user_id=int(get_jwt_identity())
    data=request.json
    task=db.session.get(Task,data['task_id'])
    if not task:
        return {"message":"Task not found"},404
    if task.assigned_to!=user_id:
        return {"message":"Not allowed"},403
    flow={"ToDo":["InProgress"],"InProgress":["Done"],"Done":[]}
    if data['status'] not in flow[task.status]:
        return {"message":"Invalid transition"},400
    task.status=data['status']
    db.session.commit()
    return {"message":"Updated"}

@app.route('/tasks',methods=['GET'])
@jwt_required()
def tasks():
    user_id=int(get_jwt_identity())
    role=get_jwt().get("role")
    query=Task.query
    if role!='Admin':
        query=query.filter(Task.assigned_to==user_id)
    tasks=query.all()
    return [{"id":t.id,"title":t.title,"status":t.status,"project_id":t.project_id,"assigned_to":t.assigned_to} for t in tasks]

@app.route('/dashboard',methods=['GET'])
@jwt_required()
def dashboard():
    user_id=int(get_jwt_identity())
    role=get_jwt().get("role")
    if role=='Admin':
        total=Task.query.count()
        todo=Task.query.filter_by(status="ToDo").count()
        prog=Task.query.filter_by(status="InProgress").count()
        done=Task.query.filter_by(status="Done").count()
    else:
        total=Task.query.filter_by(assigned_to=user_id).count()
        todo=Task.query.filter_by(assigned_to=user_id,status="ToDo").count()
        prog=Task.query.filter_by(assigned_to=user_id,status="InProgress").count()
        done=Task.query.filter_by(assigned_to=user_id,status="Done").count()
    overdue=Task.query.filter(Task.due_date<datetime.now(),Task.status!="Done").count()
    return {"total":total,"todo":todo,"inprogress":prog,"done":done,"overdue":overdue}

@app.route('/delete_task/<int:id>',methods=['DELETE'])
@jwt_required()
def delete_task(id):
    role=get_jwt().get("role")
    if role!='Admin':
        return {"message":"Only Admin"},403
    task=db.session.get(Task,id)
    if not task:
        return {"message":"Not found"},404
    db.session.delete(task)
    db.session.commit()
    return {"message":"Deleted"}

if __name__=='__main__':
    app.run(debug=True)