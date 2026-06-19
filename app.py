from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session as flask_session
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from models import db, User, Assignment, Mark, FlashcardDeck, Flashcard, TimetableEvent, Term, CustomEvent, Subject, UserSettings, AssignmentTask, Shortcut, Note, NoteLink
import os
import re
import json
import csv
import io
import pytz
from collections import defaultdict
from datetime import datetime, timezone
from dotenv import load_dotenv
from icalendar import Calendar
from study_engine import get_study_recommendations
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

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
        email = request.form.get('email', '').strip().lower()
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

        try:
            result = supabase.auth.sign_up({
                "email": email,
                "password": password,
            })
        except Exception as e:
            flash(f'Could not create account: {str(e)}', 'error')
            return render_template('register.html')

        if not result.user:
            flash('Could not create account. Try again.', 'error')
            return render_template('register.html')

        user = User(username=username, email=email, supabase_uid=result.user.id)
        db.session.add(user)
        db.session.commit()

        flash('Account created! Check your email to verify your account before logging in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        try:
            result = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })
        except Exception as e:
            flash('Invalid email or password, or email not yet verified.', 'error')
            return render_template('login.html')

        if not result.user:
            flash('Invalid email or password.', 'error')
            return render_template('login.html')

        user = User.query.filter_by(supabase_uid=result.user.id).first()
        if not user:
            user = User.query.filter_by(email=email).first()
            if user:
                user.supabase_uid = result.user.id
                db.session.commit()

        if user:
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        else:
            flash('Account not found locally. Contact support.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    logout_user()
    return redirect(url_for('login'))

# ─── Protected routes (placeholders no longer) ─────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    assignments = Assignment.query.filter_by(
        user_id=current_user.id, completed=False
    ).order_by(Assignment.due_date).limit(5).all()
    marks = Mark.query.filter_by(user_id=current_user.id).all()
    
    weighted_avg = 0
    if marks:
        active = [m for m in marks if m.active]
        if active:
            weighted_sum = sum((m.mark / m.max_mark) * m.weight for m in active)
            total_weight = sum(m.weight for m in active)
            weighted_avg = round((weighted_sum / total_weight) * 100, 1) if total_weight else 0

    decks = FlashcardDeck.query.filter_by(user_id=current_user.id).count()
    
    # Today's classes
    today = datetime.now(timezone.utc)
    today_weekday = today.weekday()  # 0=Monday
    all_events = TimetableEvent.query.filter_by(user_id=current_user.id).all()
    
    weeks = defaultdict(list)
    for e in all_events:
        wk = e.start_time.isocalendar()[:2]
        weeks[wk].append(e)
    
    today_classes = []
    if weeks:
        best_week_key = max(weeks.keys(), key=lambda wk: len(set(
            (e.day_of_week, e.period) for e in weeks[wk]
        )))
        representative = weeks[best_week_key]
        seen = set()
        for e in sorted(representative, key=lambda x: x.start_time):
            if e.day_of_week == today_weekday:
                key = (e.day_of_week, e.period, e.subject)
                if key not in seen:
                    seen.add(key)
                    today_classes.append(e)
    
    today_class_times = [
        {'subject': e.subject, 'start': e.start_time.strftime('%H:%M')}
        for e in today_classes
    ] if today_classes else []

    shortcuts = Shortcut.query.filter_by(user_id=current_user.id).all()
    
    return render_template('dashboard.html',
        user=current_user,
        assignments=assignments,
        weighted_avg=weighted_avg,
        mark_count=len(marks),
        deck_count=decks,
        today_classes=today_classes,
        shortcuts=shortcuts,
        today_class_times=today_class_times,
        now=datetime.utcnow()
    )

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
            due_date = None

            if due_date_str:
                try:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                except ValueError:
                    flash('Invalid date format. Please use the date picker.', 'error')
                    return redirect(url_for('assignments'))

            if title and subject:
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
    ).order_by(
        Assignment.due_date.asc().nullslast(),
        Assignment.id.asc()
    ).all()

    completed = Assignment.query.filter_by(
        user_id=current_user.id, completed=True
    ).order_by(Assignment.id.desc()).all()
    
    return render_template('assignments.html',
        pending=pending,
        completed=completed,
        now=datetime.utcnow()
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
                    assessment_type = request.form.get('assessment_type', 'internal'),
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
            
        elif action == 'edit':
            mark_id = int(request.form.get('mark_id'))
            m = Mark.query.filter_by(id=mark_id, user_id=current_user.id).first()
            if m:
                weight_raw = request.form.get('weight', '').strip()
                if '/' in weight_raw:
                    parts = weight_raw.split('/')
                    weight = (float(parts[0]) / float(parts[1])) * 100
                else:
                    weight = float(weight_raw.replace('%', ''))
                m.subject = request.form.get('subject', m.subject).strip()
                m.assessment_name = request.form.get('assessment_name', m.assessment_name).strip()
                m.mark = float(request.form.get('mark', m.mark))
                m.max_mark = float(request.form.get('max_mark', m.max_mark))
                m.weight = weight
                date_str = request.form.get('date', '').strip()
                if date_str:
                    m.date = datetime.strptime(date_str, '%Y-%m-%d')
                mean_val = request.form.get('mean', '').strip()
                median_val = request.form.get('median', '').strip()
                m.mean = float(mean_val) if mean_val else None
                m.median = float(median_val) if median_val else None
                m.feedback = request.form.get('feedback', '').strip()
                db.session.commit()
                flash('Mark updated.', 'success')

        return redirect(url_for('marks'))

    all_marks = Mark.query.filter_by(user_id=current_user.id).order_by(Mark.date).all()
    
    subjects = {}
    for m in all_marks:
        if m.subject not in subjects:
            subjects[m.subject] = []
        subjects[m.subject].append(m)

    return render_template('marks.html', subjects=subjects, all_marks=all_marks)

@app.route('/flashcards', methods=['GET', 'POST'])
@login_required
def flashcards():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create_deck':
            name = request.form.get('name', '').strip()
            subject = request.form.get('subject', '').strip()
            if name and subject:
                deck = FlashcardDeck(
                    user_id=current_user.id,
                    name=name,
                    subject=subject
                )
                db.session.add(deck)
                db.session.commit()
                flash('Deck created.', 'success')

        elif action == 'delete_deck':
            deck_id = int(request.form.get('deck_id'))
            deck = FlashcardDeck.query.filter_by(
                id=deck_id, user_id=current_user.id
            ).first()
            if deck:
                db.session.delete(deck)
                db.session.commit()
                flash('Deck deleted.', 'success')

        return redirect(url_for('flashcards'))

    decks = FlashcardDeck.query.filter_by(user_id=current_user.id).all()
    return render_template('flashcards.html', decks=decks, user=current_user)


@app.route('/flashcards/<int:deck_id>', methods=['GET', 'POST'])
@login_required
def flashcard_deck(deck_id):
    deck = FlashcardDeck.query.filter_by(
        id=deck_id, user_id=current_user.id
    ).first_or_404()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_card':
            question = request.form.get('question', '').strip()
            answer = request.form.get('answer', '').strip()
            if question and answer:
                card = Flashcard(deck_id=deck.id, question=question, answer=answer)
                db.session.add(card)
                db.session.commit()
                flash('Card added.', 'success')

        elif action == 'delete_card':
            card_id = int(request.form.get('card_id'))
            card = Flashcard.query.filter_by(id=card_id, deck_id=deck.id).first()
            if card:
                db.session.delete(card)
                db.session.commit()

        elif action == 'import_cards':
            import_text = request.form.get('import_text', '').strip()
            separator = request.form.get('separator', ',')
            if import_text:
                lines = import_text.strip().split('\n')
                added = 0
                skipped = 0
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if separator in line:
                        parts = line.split(separator, 1)
                        question = parts[0].strip()
                        answer = parts[1].strip()
                        if question and answer:
                            card = Flashcard(
                                deck_id=deck.id,
                                question=question,
                                answer=answer
                            )
                            db.session.add(card)
                            added += 1
                    else:
                        skipped += 1
                db.session.commit()
                flash(f'{added} cards imported.{" " + str(skipped) + " lines skipped (no separator found)." if skipped else ""}', 'success')

        elif action == 'import_csv':
            file = request.files.get('csv_file')
            if file and file.filename.endswith('.csv'):
                stream = io.StringIO(file.stream.read().decode('utf-8'))
                reader = csv.reader(stream)
                added = 0
                for row in reader:
                    if len(row) >= 2:
                        question = row[0].strip()
                        answer = row[1].strip()
                        if question and answer:
                            card = Flashcard(
                                deck_id=deck.id,
                                question=question,
                                answer=answer
                            )
                            db.session.add(card)
                            added += 1
                db.session.commit()
                flash(f'{added} cards imported from CSV.', 'success')
            else:
                flash('Please upload a valid .csv file.', 'error')

        return redirect(url_for('flashcard_deck', deck_id=deck.id))

    cards = Flashcard.query.filter_by(deck_id=deck.id).all()
    return render_template('flashcard_deck.html', deck=deck, cards=cards)

@app.route('/flashcards/<int:deck_id>/quiz')
@login_required
def quiz(deck_id):
    deck = FlashcardDeck.query.filter_by(
        id=deck_id, user_id=current_user.id
    ).first_or_404()
    cards_raw = Flashcard.query.filter_by(deck_id=deck.id).all()
    cards = [{'question': c.question, 'answer': c.answer, 'id': c.id} for c in cards_raw]
    return render_template('quiz.html', deck=deck, cards=cards)

@app.route('/flashcards/<int:deck_id>/complete', methods=['POST'])
@login_required
def quiz_complete(deck_id):
    data = request.get_json()
    today = datetime.now(timezone.utc).date()
    user = current_user

    last = user.last_studied
    if last:
        last_date = last.date() if hasattr(last, 'date') else last
        diff = (today - last_date).days
        if diff == 1:
            user.streak = (user.streak or 0) + 1
        elif diff > 1:
            user.streak = 1
    else:
        user.streak = 1

    user.last_studied = datetime.now(timezone.utc)

    # Set retention quiz due in 3 days
    deck = FlashcardDeck.query.filter_by(id=deck_id, user_id=current_user.id).first()
    if deck:
        deck.last_completed = datetime.now(timezone.utc)
        deck.retention_due = datetime.now(timezone.utc) + timedelta(days=3)

    db.session.commit()
    return jsonify({'streak': user.streak})

@app.route('/timetable', methods=['GET', 'POST'])
@login_required
def timetable():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'import_ics':            
            file = request.files.get('ics_file')
            term_id = request.form.get('term_id') or None
            timezone_str = request.form.get('timezone', 'Australia/Sydney')
            local_tz = pytz.timezone(timezone_str)

            if file and file.filename.endswith('.ics'):
                TimetableEvent.query.filter_by(
                    user_id=current_user.id,
                    is_manual=False,
                    term_id=term_id
                ).delete()
                db.session.commit()

                cal = Calendar.from_ical(file.stream.read())
                added = 0
                skipped = 0

                for component in cal.walk():
                    if component.name != 'VEVENT':
                        continue

                    summary = str(component.get('SUMMARY', ''))
                    description = str(component.get('DESCRIPTION', ''))
                    location = str(component.get('LOCATION', ''))
                    dtstart = component.get('DTSTART').dt
                    dtend = component.get('DTEND').dt

                    if hasattr(dtstart, 'hour'):
                        if dtstart.tzinfo is not None:
                            dtstart = dtstart.astimezone(local_tz).replace(tzinfo=None)
                            dtend = dtend.astimezone(local_tz).replace(tzinfo=None)
                    else:
                        skipped += 1
                        continue

                    if ':' in summary:
                        parts = summary.split(':', 1)
                        class_code = parts[0].strip()
                        subject = parts[1].strip()
                    else:
                        class_code = ''
                        subject = summary.strip()

                    teacher = ''
                    period = ''
                    for line in description.replace('\\n', '\n').split('\n'):
                        if line.startswith('Teacher:'):
                            teacher = line.replace('Teacher:', '').strip()
                        elif line.startswith('Period:'):
                            period = line.replace('Period:', '').strip()

                    room = location.replace('Room:', '').strip()

                    if 'Roll Call' in period or 'Roll' in subject:
                        skipped += 1
                        continue

                    event = TimetableEvent(
                        user_id=current_user.id,
                        term_id=term_id,
                        subject=subject,
                        class_code=class_code,
                        teacher=teacher,
                        room=room,
                        period=period,
                        start_time=dtstart,
                        end_time=dtend,
                        day_of_week=dtstart.weekday(),
                        is_manual=False,
                        event_type='class'
                    )
                    db.session.add(event)
                    added += 1

                db.session.commit()
                unique_subjects = {}
                for event in TimetableEvent.query.filter_by(
                    user_id=current_user.id
                ).all():
                    if event.subject not in unique_subjects:
                        unique_subjects[event.subject] = {
                            'class_code': event.class_code,
                            'teacher': event.teacher,
                            'room': event.room
                        }
                flask_session['pending_subjects'] = unique_subjects
                flash(f'Imported {added} classes. Now select which subjects to add to your markbook.', 'success')
                return redirect(url_for('setup_subjects'))
            else:
                flash('Please upload a valid .ics file.', 'error')

        elif action == 'add_term':
            name = request.form.get('term_name', '').strip()
            start = request.form.get('term_start', '').strip()
            end = request.form.get('term_end', '').strip()
            if name and start and end:
                term = Term(
                    user_id=current_user.id,
                    name=name,
                    start_date=datetime.strptime(start, '%Y-%m-%d'),
                    end_date=datetime.strptime(end, '%Y-%m-%d'),
                    is_active=True
                )
                db.session.add(term)
                db.session.commit()
                flash(f'Term "{name}" added.', 'success')

        elif action == 'set_active_term':
            term_id = int(request.form.get('term_id'))
            Term.query.filter_by(user_id=current_user.id).update({'is_active': False})
            term = Term.query.filter_by(id=term_id, user_id=current_user.id).first()
            if term:
                term.is_active = True
            db.session.commit()

        elif action == 'add_custom_event':
            title = request.form.get('title', '').strip()
            start = request.form.get('start_time', '').strip()
            end = request.form.get('end_time', '').strip()
            event_type = request.form.get('event_type', 'event')
            description = request.form.get('description', '').strip()
            if title and start:
                event = CustomEvent(
                    user_id=current_user.id,
                    title=title,
                    description=description,
                    start_time=datetime.strptime(start, '%Y-%m-%dT%H:%M'),
                    end_time=datetime.strptime(end, '%Y-%m-%dT%H:%M') if end else None,
                    event_type=event_type
                )
                db.session.add(event)
                db.session.commit()
                flash('Event added.', 'success')

        return redirect(url_for('timetable'))

    active_term = Term.query.filter_by(
        user_id=current_user.id, is_active=True
    ).first()
    all_terms = Term.query.filter_by(user_id=current_user.id).all()

    events = TimetableEvent.query.filter_by(
        user_id=current_user.id
    ).order_by(TimetableEvent.start_time).all()

    all_events = TimetableEvent.query.filter_by(
        user_id=current_user.id
    ).order_by(TimetableEvent.start_time).all()

    def get_week_key(d):
        return d.isocalendar()[:2]

    weeks = defaultdict(list)
    for e in all_events:
        wk = get_week_key(e.start_time)
        weeks[wk].append(e)

    if not weeks:
        best_week_key = None
    else:
        best_week_key = max(weeks.keys(), key=lambda wk: len(set(
            (e.day_of_week, e.period) for e in weeks[wk]
        )))
    representative_events = weeks[best_week_key]

    seen = set()
    unique_events = []
    for e in representative_events:
        key = (e.day_of_week, e.period, e.subject)
        if key not in seen:
            seen.add(key)
            unique_events.append(e)

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    period_order = ['Period 1', 'Period 2', 'Period 3', 'Period 4',
                    'Period 5', 'Period 6', 'Period 7', 'Period 8']

    periods_present = sorted(
        set(e.period for e in unique_events if e.period),
        key=lambda p: period_order.index(p) if p in period_order else 99
    )

    timetable_grid = {}
    for period in periods_present:
        timetable_grid[period] = {}
        for i, day in enumerate(days):
            match = next(
                (e for e in unique_events if e.day_of_week == i and e.period == period),
                None
            )
            timetable_grid[period][day] = match

    custom_events = CustomEvent.query.filter_by(
        user_id=current_user.id
    ).order_by(CustomEvent.start_time).all()

    return render_template('timetable.html',
        timetable_grid=timetable_grid,
        days=days,
        periods=periods_present,
        terms=all_terms,
        active_term=active_term,
        custom_events=custom_events
    )

@app.route('/timetable/setup-subjects', methods=['GET', 'POST'])
@login_required
def setup_subjects():
    pending = flask_session.get('pending_subjects', {})
    
    if request.method == 'POST':
        selected = request.form.getlist('subjects')
        for subject_name in selected:
            existing = Subject.query.filter_by(
                user_id=current_user.id,
                name=subject_name
            ).first()
            if not existing and subject_name in pending:
                info = pending[subject_name]
                subject = Subject(
                    user_id=current_user.id,
                    name=subject_name,
                    class_code=info.get('class_code', ''),
                    teacher=info.get('teacher', ''),
                    room=info.get('room', ''),
                    is_graded=True
                )
                db.session.add(subject)
        db.session.commit()
        flask_session.pop('pending_subjects', None)
        flash('Subjects added to your markbook.', 'success')
        return redirect(url_for('timetable'))

    return render_template('setup_subjects.html', pending=pending)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    settings = UserSettings.query.filter_by(user_id=current_user.id).first()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.session.add(settings)
        db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'save_general':
            current_user.display_name = request.form.get('display_name', '').strip() or None
            settings.school_name = request.form.get('school_name', '').strip()
            settings.num_terms = int(request.form.get('num_terms', 4))
            settings.year_level = request.form.get('year_level', '').strip()
            settings.timezone = request.form.get('timezone', 'Australia/Sydney')
            settings.font_family = request.form.get('font_family', 'Inter').strip()
            settings.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Settings saved.', 'success')

        elif action == 'save_grading':
            grades = request.form.getlist('grade_label')
            mins = request.form.getlist('grade_min')
            maxs = request.form.getlist('grade_max')
            scale = []
            for label, mn, mx in zip(grades, mins, maxs):
                if label.strip() and mn and mx:
                    scale.append({
                        'label': label.strip(),
                        'min': float(mn),
                        'max': float(mx)
                    })
            settings.grading_scale = json.dumps(scale)
            settings.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Grading scale saved.', 'success')

        elif action == 'change_password':
            new_pw = request.form.get('new_password', '')
            if len(new_pw) < 8:
                flash('New password must be at least 8 characters.', 'error')
            else:
                try:
                    supabase.auth.update_user({"password": new_pw})
                    flash('Password updated.', 'success')
                except Exception as e:
                    flash(f'Could not update password: {str(e)}', 'error')

        elif action == 'change_username':
            new_username = request.form.get('new_username', '').strip()
            if User.query.filter_by(username=new_username).first():
                flash('That username is taken.', 'error')
            elif len(new_username) < 3:
                flash('Username must be at least 3 characters.', 'error')
            else:
                current_user.username = new_username
                db.session.commit()
                flash('Username updated.', 'success')

        elif action == 'delete_account':
            confirm = request.form.get('confirm_delete', '')
            if confirm == current_user.username:
                db.session.delete(current_user)
                db.session.commit()
                flash('Account deleted.', 'success')
                return redirect(url_for('index'))
            else:
                flash('Username did not match. Account not deleted.', 'error')

        return redirect(url_for('settings'))

    grading_scale = []
    if settings.grading_scale:
        grading_scale = json.loads(settings.grading_scale)

    subjects = Subject.query.filter_by(user_id=current_user.id).all()

    return render_template('settings.html',
        settings=settings,
        grading_scale=grading_scale,
        subjects=subjects
    )

@app.route('/settings/delete-subject/<int:subject_id>', methods=['POST'])
@login_required
def delete_subject(subject_id):
    subject = Subject.query.filter_by(
        id=subject_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(subject)
    db.session.commit()
    flash(f'Removed {subject.name} from markbook.', 'success')
    return redirect(url_for('settings'))

@app.route('/analytics')
@login_required
def analytics():
    all_marks = Mark.query.filter_by(
        user_id=current_user.id
    ).order_by(Mark.date).all()

    subjects = {}
    for m in all_marks:
        if m.subject not in subjects:
            subjects[m.subject] = []
        subjects[m.subject].append(m)

    subject_averages = {}
    for subject, marks in subjects.items():
        active = [m for m in marks if m.active]
        if active:
            weighted_sum = sum((m.mark / m.max_mark) * m.weight for m in active)
            total_weight = sum(m.weight for m in active)
            avg = round((weighted_sum / total_weight) * 100, 1) if total_weight else 0
            subject_averages[subject] = avg

    settings = UserSettings.query.filter_by(user_id=current_user.id).first()
    grading_scale = []
    if settings and settings.grading_scale:
        grading_scale = json.loads(settings.grading_scale)

    def get_grade(score):
        for g in sorted(grading_scale, key=lambda x: x['min'], reverse=True):
            if score >= g['min']:
                return g['label']
        return '—'

    chart_data = {}
    for subject, marks in subjects.items():
        active = [m for m in marks if m.active]
        chart_data[subject] = {
            'labels': [m.assessment_name for m in active],
            'raw': [round(m.mark / m.max_mark * 100, 1) for m in active],
            'weighted': [round(m.mark / m.max_mark * m.weight, 1) for m in active],
            'mean': [m.mean if m.mean else None for m in active],
            'dates': [m.date.strftime('%d %b') for m in active],
            'average': subject_averages.get(subject, 0),
            'grade': get_grade(subject_averages.get(subject, 0))
        }

    return render_template('analytics.html',
        subjects=subjects,
        subject_averages=subject_averages,
        chart_data=json.dumps(chart_data),
        grading_scale=grading_scale,
        get_grade=get_grade
    )

@app.route('/analytics/set-benchmark', methods=['POST'])
@login_required
def set_subject_benchmark():
    subject_name = request.form.get('subject_name', '').strip()
    benchmark = request.form.get('benchmark', '').strip()
    subject = Subject.query.filter_by(
        user_id=current_user.id, name=subject_name
    ).first()
    if subject and benchmark:
        subject.benchmark = float(benchmark)
        db.session.commit()
        flash(f'Benchmark set for {subject_name}.', 'success')
    return redirect(url_for('analytics'))

@app.route('/assignments/<int:assignment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_assignment(assignment_id):
    assignment = Assignment.query.filter_by(
        id=assignment_id, user_id=current_user.id
    ).first_or_404()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'edit':
            assignment.title = request.form.get('title', assignment.title).strip()
            assignment.subject = request.form.get('subject', assignment.subject).strip()
            due_date_str = request.form.get('due_date', '').strip()
            if due_date_str:
                assignment.due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
            assignment.priority = int(request.form.get('priority', assignment.priority))
            db.session.commit()
            flash('Assignment updated.', 'success')
        
        elif action == 'add_task':
            title = request.form.get('task_title', '').strip()
            if title:
                task = AssignmentTask(
                    assignment_id=assignment.id,
                    title=title
                )
                db.session.add(task)
                db.session.commit()
        
        elif action == 'toggle_task':
            task_id = int(request.form.get('task_id'))
            task = AssignmentTask.query.filter_by(
                id=task_id, assignment_id=assignment.id
            ).first()
            if task:
                task.completed = not task.completed
                db.session.commit()
        
        elif action == 'delete_task':
            task_id = int(request.form.get('task_id'))
            task = AssignmentTask.query.filter_by(
                id=task_id, assignment_id=assignment.id
            ).first()
            if task:
                db.session.delete(task)
                db.session.commit()
        
        return redirect(url_for('edit_assignment', assignment_id=assignment.id))
    
    return render_template('edit_assignment.html', assignment=assignment)

@app.route('/study')
@login_required
def study():
    all_marks = Mark.query.filter_by(user_id=current_user.id).all()
    pending_assignments = Assignment.query.filter_by(
        user_id=current_user.id, completed=False
    ).order_by(Assignment.due_date).all()
    decks = FlashcardDeck.query.filter_by(user_id=current_user.id).all()
    
    recommendations = get_study_recommendations(
        all_marks, pending_assignments, decks, current_user.streak or 0
    )
    
    return render_template('study.html',
        recommendations=recommendations,
        user=current_user
    )

@app.route('/retention-check')
@login_required
def retention_check():
    now = datetime.now(timezone.utc)
    due_decks = FlashcardDeck.query.filter(
        FlashcardDeck.user_id == current_user.id,
        FlashcardDeck.retention_due <= now,
        FlashcardDeck.retention_due != None
    ).all()
    return jsonify([{
        'id': d.id,
        'name': d.name,
        'subject': d.subject,
        'due': d.retention_due.isoformat()
    } for d in due_decks])

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/shortcuts/add', methods=['POST'])
@login_required
def add_shortcut():
    name = request.form.get('name', '').strip()
    url = request.form.get('url', '').strip()
    icon = request.form.get('icon', '🔗').strip() or '🔗'
    if name and url:
        if not url.startswith('http'):
            url = 'https://' + url
        shortcut = Shortcut(user_id=current_user.id, name=name, url=url, icon=icon)
        db.session.add(shortcut)
        db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/shortcuts/<int:shortcut_id>/delete', methods=['POST'])
@login_required
def delete_shortcut(shortcut_id):
    shortcut = Shortcut.query.filter_by(id=shortcut_id, user_id=current_user.id).first_or_404()
    db.session.delete(shortcut)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/notes', methods=['GET', 'POST'])
@login_required
def notes():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            title = request.form.get('title', '').strip()
            subject = request.form.get('subject', '').strip() or None
            content = request.form.get('content', '').strip() or None
            if title:
                note = Note(user_id=current_user.id, title=title, subject=subject, content=content)
                db.session.add(note)
                db.session.flush()
                labels = request.form.getlist('link_label[]')
                urls = request.form.getlist('link_url[]')
                for label, url_val in zip(labels, urls):
                    url_val = url_val.strip()
                    if url_val:
                        db.session.add(NoteLink(note_id=note.id, label=label.strip() or url_val, url=url_val))
                db.session.commit()
        elif action == 'delete':
            note_id = request.form.get('note_id', type=int)
            note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
            if note:
                db.session.delete(note)
                db.session.commit()
        return redirect(url_for('notes'))

    subject_filter = request.args.get('subject', '')
    query = Note.query.filter_by(user_id=current_user.id)
    if subject_filter:
        query = query.filter_by(subject=subject_filter)
    all_notes = query.order_by(Note.updated_at.desc()).all()

    subjects_raw = db.session.query(Note.subject).filter_by(user_id=current_user.id).distinct().all()
    note_subjects = sorted([s[0] for s in subjects_raw if s[0]])
    user_subjects = Subject.query.filter_by(user_id=current_user.id).all()

    return render_template('notes.html', notes=all_notes, note_subjects=note_subjects,
                           user_subjects=user_subjects, active_subject=subject_filter)


@app.route('/notes/<int:note_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        note.title = request.form.get('title', '').strip() or note.title
        note.subject = request.form.get('subject', '').strip() or None
        note.content = request.form.get('content', '').strip() or None
        note.updated_at = datetime.utcnow()
        NoteLink.query.filter_by(note_id=note.id).delete()
        labels = request.form.getlist('link_label[]')
        urls = request.form.getlist('link_url[]')
        for label, url_val in zip(labels, urls):
            url_val = url_val.strip()
            if url_val:
                db.session.add(NoteLink(note_id=note.id, label=label.strip() or url_val, url=url_val))
        db.session.commit()
        return redirect(url_for('notes'))
    user_subjects = Subject.query.filter_by(user_id=current_user.id).all()
    return render_template('edit_note.html', note=note, user_subjects=user_subjects)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        try:
            supabase.auth.reset_password_for_email(email, {
                "redirect_to": url_for('reset_password', _external=True)
            })
        except Exception:
            pass  # Don't leak whether email exists
        return render_template('forgot_password.html', sent=True)
    return render_template('forgot_password.html', sent=False)


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        new_password = request.form.get('password', '')
        access_token = request.form.get('access_token', '')
        if len(new_password) < 8:
            return render_template('reset_password.html', error='Password must be at least 8 characters.')
        try:
            supabase.auth.update_user({"password": new_password}, access_token)
            return render_template('reset_password.html', success=True)
        except Exception as e:
            return render_template('reset_password.html', error=str(e))
    return render_template('reset_password.html')

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_ENV') == 'development')