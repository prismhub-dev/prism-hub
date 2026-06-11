from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from models import db, User, Assignment, Mark, FlashcardDeck, Flashcard
import os
from dotenv import load_dotenv
import bcrypt
from datetime import datetime, timezone

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── Public routes ───────────────────────────────────────────────
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return render_template('register.html')
        if User.query.filter_by(username=username).first():
            flash('That username is taken.', 'error')
            return render_template('register.html')

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        user = User(username=username, email=email, password=hashed.decode('utf-8'))
        db.session.add(user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ─── Protected routes (placeholders for now) ─────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    assignments = Assignment.query.filter_by(
        user_id=current_user.id, completed=False
    ).order_by(Assignment.due_date).limit(5).all()
    marks = Mark.query.filter_by(user_id=current_user.id).all()
    
    weighted_avg = 0
    if marks:
        weighted_sum = sum((m.mark / m.max_mark) * m.weight for m in marks)
        total_weight = sum(m.weight for m in marks)
        weighted_avg = round((weighted_sum / total_weight) * 100, 1) if total_weight else 0

    decks = FlashcardDeck.query.filter_by(user_id=current_user.id).count()
    
    return render_template('dashboard.html',
        user=current_user,
        assignments=assignments,
        weighted_avg=weighted_avg,
        mark_count=len(marks),
        deck_count=decks,
        now=datetime.now(timezone.utc)
    )

@app.route('/flashcards')
@login_required
def flashcards():
    return render_template('flashcards.html')

@app.route('/assignments', methods=['GET', 'POST'])
@login_required
def assignments():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            title = request.form.get('title', '').strip()
            subject = request.form.get('subject', '').strip()
            due_date_str = request.form.get('due_date', '').strip()
            priority = int(request.form.get('priority', 2))
            
            if title and subject and due_date_str:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                assignment = Assignment(
                    user_id=current_user.id,
                    title=title,
                    subject=subject,
                    due_date=due_date,
                    priority=priority
                )
                db.session.add(assignment)
                db.session.commit()
                flash('Assignment added.', 'success')
        
        elif action == 'toggle':
            assignment_id = int(request.form.get('assignment_id'))
            assignment = Assignment.query.filter_by(
                id=assignment_id, user_id=current_user.id
            ).first()
            if assignment:
                assignment.completed = not assignment.completed
                db.session.commit()
        
        elif action == 'delete':
            assignment_id = int(request.form.get('assignment_id'))
            assignment = Assignment.query.filter_by(
                id=assignment_id, user_id=current_user.id
            ).first()
            if assignment:
                db.session.delete(assignment)
                db.session.commit()
                flash('Assignment deleted.', 'success')
        
        return redirect(url_for('assignments'))
    
    pending = Assignment.query.filter_by(
        user_id=current_user.id, completed=False
    ).order_by(Assignment.due_date).all()
    completed = Assignment.query.filter_by(
        user_id=current_user.id, completed=True
    ).order_by(Assignment.due_date.desc()).limit(10).all()
    
    return render_template('assignments.html',
        pending=pending,
        completed=completed,
        now=datetime.now(timezone.utc)
    )


@app.route('/marks', methods=['GET', 'POST'])
@login_required
def marks():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            subject = request.form.get('subject', '').strip()
            assessment_name = request.form.get('assessment_name', '').strip()
            mark = request.form.get('mark', '').strip()
            max_mark = request.form.get('max_mark', '').strip()
            weight_raw = request.form.get('weight', '').strip()
            date_str = request.form.get('date', '').strip()
            mean = request.form.get('mean', '').strip()
            median = request.form.get('median', '').strip()
            feedback = request.form.get('feedback', '').strip()

            if subject and assessment_name and mark and max_mark and weight_raw:
                import re
                if '/' in weight_raw:
                    parts = weight_raw.split('/')
                    weight = (float(parts[0]) / float(parts[1])) * 100
                else:
                    weight = float(weight_raw.replace('%', ''))
                
                date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()
                
                new_mark = Mark(
                    user_id=current_user.id,
                    subject=subject,
                    assessment_name=assessment_name,
                    mark=float(mark),
                    max_mark=float(max_mark),
                    weight=weight,
                    date=date
                )
                db.session.add(new_mark)
                db.session.commit()
                flash('Mark added.', 'success')
        
        elif action == 'toggle':
            mark_id = int(request.form.get('mark_id'))
            m = Mark.query.filter_by(id=mark_id, user_id=current_user.id).first()
            if m:
                m.active = not m.active
                db.session.commit()

        elif action == 'delete':
            mark_id = int(request.form.get('mark_id'))
            m = Mark.query.filter_by(id=mark_id, user_id=current_user.id).first()
            if m:
                db.session.delete(m)
                db.session.commit()
                flash('Mark deleted.', 'success')

        return redirect(url_for('marks'))

    all_marks = Mark.query.filter_by(user_id=current_user.id).order_by(Mark.date).all()
    
    subjects = {}
    for m in all_marks:
        if m.subject not in subjects:
            subjects[m.subject] = []
        subjects[m.subject].append(m)

    return render_template('marks.html', subjects=subjects, all_marks=all_marks)

if __name__ == '__main__':
    app.run(debug=True)