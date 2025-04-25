from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import or_, select
from flask_migrate import Migrate


app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shc_medix.db'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    role = db.Column(db.String(10))

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="Pending")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, nullable=False)
    receiver_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)  # <== This is missing
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    seen = db.Column(db.Boolean, default=False)

@app.route('/')
def index():
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        if user:
            return redirect(url_for(f"{user.role}_dashboard"))
        session.pop('user_id', None)  # Clear invalid session
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = db.session.execute(
            select(User).where(User.email == email, User.password == password)
        ).scalar_one_or_none()
        
        if user:
            session['user_id'] = user.id
            return redirect(url_for(f"{user.role}_dashboard"))
        flash('Invalid email or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        doctor_keyword = request.form.get('doctor_keyword', '')

        # Check if email exists
        if db.session.execute(select(User).where(User.email == email)).scalar_one_or_none():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))

        if role == 'doctor' and doctor_keyword.lower() != 'doctor':
            flash('Invalid doctor keyword', 'error')
            return redirect(url_for('register'))

        new_user = User(name=name, email=email, password=password, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/patient_dashboard')
def patient_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = db.session.get(User, session['user_id'])
    if not user or user.role != 'patient':
        return redirect(url_for('index'))

    doctors = db.session.execute(select(User).where(User.role == 'doctor')).scalars().all()

    appointments_raw = db.session.execute(
        select(Appointment).where(Appointment.patient_id == user.id)
    ).scalars().all()
    
    appointments = []
    for appt in appointments_raw:
        doctor = db.session.get(User, appt.doctor_id)
        appointments.append({
            'id': appt.id,
            'doctor_id': appt.doctor_id,
            'doctor_name': doctor.name if doctor else 'Unknown Doctor',
            'date_time': appt.date_time.strftime('%Y-%m-%d %H:%M') if appt.date_time else 'No date set',
            'status': appt.status
        })

    current_time = datetime.now().strftime('%Y-%m-%dT%H:%M')

    return render_template(
        'patient_dashboard.html',
        user=user,
        doctors=doctors,
        appointments=appointments,
        current_time=current_time
    )

@app.route('/doctor_dashboard')
def doctor_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = db.session.get(User, session['user_id'])
    if not user or user.role != 'doctor':
        return redirect(url_for('index'))

    # Get pending appointments with patient names
    pending_appointments = []
    pending_query = db.session.execute(
        select(Appointment, User.name)
        .join(User, Appointment.patient_id == User.id)
        .where(Appointment.doctor_id == user.id, Appointment.status == 'Pending')
    ).all()
    
    for appt, patient_name in pending_query:
        pending_appointments.append({
            'id': appt.id,
            'patient_id': appt.patient_id,
            'patient_name': patient_name,
            'date_time': appt.date_time.strftime('%Y-%m-%d %H:%M') if appt.date_time else 'No date set',
            'status': appt.status
        })

    # Get confirmed appointments
    confirmed_appointments = []
    confirmed_query = db.session.execute(
        select(Appointment, User.name)
        .join(User, Appointment.patient_id == User.id)
        .where(Appointment.doctor_id == user.id, Appointment.status == 'Confirmed')
    ).all()
    
    for appt, patient_name in confirmed_query:
        confirmed_appointments.append({
            'id': appt.id,
            'patient_id': appt.patient_id,
            'patient_name': patient_name,
            'date_time': appt.date_time.strftime('%Y-%m-%d %H:%M') if appt.date_time else 'No date set',
            'status': appt.status
        })

    
    return render_template(
        'doctor_dashboard.html',
        user=user,
        pending_appointments=pending_appointments,
        confirmed_appointments=confirmed_appointments
    )



@app.route('/recent_chats')
def recent_chats():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(User, session['user_id'])
    if not user or user.role != 'doctor':
        return redirect(url_for('index'))

    chat_query = db.session.execute(
        select(Message, User.name)
        .join(User, or_(
            (Message.sender_id == User.id) & (Message.receiver_id == user.id),
            (Message.receiver_id == User.id) & (Message.sender_id == user.id)
        ))
        .where(or_(
            Message.sender_id == user.id,
            Message.receiver_id == user.id
        ))
        .order_by(Message.timestamp.desc())
        .limit(10)
    ).all()

    chats = []
    for msg, other_user_name in chat_query:
        chats.append({
            'sender_id': msg.sender_id,
            'receiver_id': msg.receiver_id,
            'message': msg.message,
            'timestamp': msg.timestamp,
            'other_user_name': other_user_name
        })

    return render_template('recent.html', user=user, chats=chats)

@app.route('/schedule_appointment', methods=['POST'])
def schedule_appointment():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    patient_id = session['user_id']
    doctor_id = request.form['doctor_id']
    date_time = datetime.fromisoformat(request.form['date_time'])
    
    # Check if there's already an appointment for the same doctor at the same time
    existing_appointment = Appointment.query.filter_by(
        doctor_id=doctor_id, 
        date_time=date_time
    ).first()

    if existing_appointment:
        # If an appointment already exists, prevent new booking
        flash('The doctor is already booked at this time. Please choose another time.', 'error')
        return redirect(url_for('patient_dashboard'))

    # If no existing appointment is found, create a new appointment
    new_appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        date_time=date_time
    )

    db.session.add(new_appointment)
    db.session.commit()
    flash('Appointment scheduled successfully!', 'success')
    return redirect(url_for('patient_dashboard'))

@app.route('/confirm_appointment/<int:appointment_id>')
def confirm_appointment(appointment_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = db.session.get(User, session['user_id'])
    if not user or user.role != 'doctor':
        flash('Only doctors can confirm appointments', 'error')
        return redirect(url_for('index'))
    
    appointment = db.session.get(Appointment, appointment_id)
    if not appointment or appointment.doctor_id != user.id:
        flash('Appointment not found or not assigned to you', 'error')
        return redirect(url_for('doctor_dashboard'))
    
    appointment.status = "Confirmed"
    db.session.commit()
    flash('Appointment confirmed successfully', 'success')
    return redirect(url_for('doctor_dashboard'))

@app.route('/reject_appointment/<int:appointment_id>')
def reject_appointment(appointment_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = db.session.get(User, session['user_id'])
    if not user or user.role != 'doctor':
        flash('Only doctors can reject appointments', 'error')
        return redirect(url_for('index'))
    
    appointment = db.session.get(Appointment, appointment_id)
    if not appointment or appointment.doctor_id != user.id:
        flash('Appointment not found or not assigned to you', 'error')
        return redirect(url_for('doctor_dashboard'))
    
    appointment.status = "Rejected"
    db.session.commit()
    flash('Appointment rejected', 'info')
    return redirect(url_for('doctor_dashboard'))

@app.route('/get_unread_count')
def get_unread_count():
    if 'user_id' not in session:
        return jsonify({'unread_count': 0})
    
    count = Message.query.filter_by(receiver_id=session['user_id'], seen=False).count()
    return jsonify({'unread_count': count})


@app.route('/patient_chat/<int:doctor_id>', methods=['GET', 'POST'])
def patient_chat(doctor_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    patient = db.session.get(User, session['user_id'])
    doctor = db.session.get(User, doctor_id)
    
    if not patient or not doctor or patient.role != 'patient':
        return redirect(url_for('index'))

    if request.method == 'POST':
        content = request.form['message']
        new_message = Message(
            sender_id=patient.id,
            receiver_id=doctor.id,
            message=content,
            seen=False
        )
        db.session.add(new_message)
        db.session.commit()
        return redirect(url_for('patient_chat', doctor_id=doctor_id))

    Message.query.filter_by(
        sender_id=patient.id,
        receiver_id=doctor.id,
        seen=False
    ).update({'seen': True})

    db.session.commit()

    messages = db.session.execute(
        select(Message)
        .where(or_(
            (Message.sender_id == patient.id) & (Message.receiver_id == doctor.id),
            (Message.sender_id == doctor.id) & (Message.receiver_id == patient.id)
        ))
        .order_by(Message.timestamp)
    ).scalars().all()

    return render_template(
        'chat.html',
        user=patient,
        other_user=doctor,
        messages=messages,
        chat_endpoint='patient_chat'
    )

@app.route('/doctor_chat/<int:patient_id>', methods=['GET', 'POST'])
def doctor_chat(patient_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    doctor = db.session.get(User, session['user_id'])
    patient = db.session.get(User, patient_id)
    
    if not doctor or not patient or doctor.role != 'doctor':
        return redirect(url_for('index'))

    if request.method == 'POST':
        content = request.form['message']
        new_message = Message(
            sender_id=doctor.id,
            receiver_id=patient.id,
            message=content,
            seen=False
        )
        db.session.add(new_message)
        db.session.commit()
        return redirect(url_for('doctor_chat', patient_id=patient_id))
    
    Message.query.filter_by(
        sender_id=patient.id,
        receiver_id=doctor.id,
        seen=False
    ).update({'seen': True})

    db.session.commit()


    messages = db.session.execute(
        select(Message)
        .where(or_(
            (Message.sender_id == doctor.id) & (Message.receiver_id == patient.id),
            (Message.sender_id == patient.id) & (Message.receiver_id == doctor.id)
        ))
        .order_by(Message.timestamp)
    ).scalars().all()

    return render_template(
        'chat.html',
        user=doctor,
        other_user=patient,
        messages=messages,
        chat_endpoint='doctor_chat'
    )

if __name__ == '__main__':
    # with app.app_context():
        # db.create_all()
    # migrate = Migrate(app, db)
    app.run(debug=True)