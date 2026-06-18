from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assignments = db.relationship('Assignment', backref='user', lazy=True)
    marks = db.relationship('Mark', backref='user', lazy=True)
    flashcard_decks = db.relationship('FlashcardDeck', backref='user', lazy=True)
    streak = db.Column(db.Integer, default=0)
    last_studied = db.Column(db.DateTime, nullable=True)
    display_name = db.Column(db.String(100), nullable=True)
    settings = db.relationship('UserSettings', backref='user', uselist=False, lazy=True)

class Assignment(db.Model):
    __tablename__ = 'assignments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    due_date = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.Integer, default=2)
    completed = db.Column(db.Boolean, default=False)
    tasks = db.relationship('AssignmentTask', backref='assignment', lazy=True, cascade='all, delete-orphan')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Mark(db.Model):
    __tablename__ = 'marks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    assessment_name = db.Column(db.String(200), nullable=False)
    mark = db.Column(db.Float, nullable=False)
    max_mark = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    active = db.Column(db.Boolean, default=True)
    mean = db.Column(db.Float, nullable=True)
    median = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    assessment_type = db.Column(db.String(50), default='internal')
    date = db.Column(db.DateTime, default=datetime.utcnow)

class FlashcardDeck(db.Model):
    __tablename__ = 'flashcard_decks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_completed = db.Column(db.DateTime, nullable=True)      # ← add
    retention_due = db.Column(db.DateTime, nullable=True)       # ← add
    cards = db.relationship('Flashcard', backref='deck', lazy=True)

class Flashcard(db.Model):
    __tablename__ = 'flashcards'
    id = db.Column(db.Integer, primary_key=True)
    deck_id = db.Column(db.Integer, db.ForeignKey('flashcard_decks.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    last_reviewed = db.Column(db.DateTime, nullable=True)
    retention_score = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TimetableEvent(db.Model):
    __tablename__ = 'timetable_events'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=True)
    subject = db.Column(db.String(200), nullable=False)
    class_code = db.Column(db.String(50), nullable=True)
    teacher = db.Column(db.String(200), nullable=True)
    room = db.Column(db.String(50), nullable=True)
    period = db.Column(db.String(50), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    is_manual = db.Column(db.Boolean, default=False)
    event_type = db.Column(db.String(50), default='class')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Term(db.Model):
    __tablename__ = 'terms'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CustomEvent(db.Model):
    __tablename__ = 'custom_events'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    event_type = db.Column(db.String(50), default='event')
    is_recurring = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    class_code = db.Column(db.String(50), nullable=True)
    teacher = db.Column(db.String(200), nullable=True)
    room = db.Column(db.String(50), nullable=True)
    color = db.Column(db.String(20), default='#C9A84C')
    is_graded = db.Column(db.Boolean, default=True)
    benchmark = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserSettings(db.Model):
    __tablename__ = 'user_settings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    school_name = db.Column(db.String(200), nullable=True)
    num_terms = db.Column(db.Integer, default=4)
    year_level = db.Column(db.String(20), nullable=True)
    timezone = db.Column(db.String(50), default='Australia/Sydney')
    theme = db.Column(db.String(20), default='dark')
    notifications_enabled = db.Column(db.Boolean, default=False)
    grading_scale = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    font_family = db.Column(db.String(50), default='Inter')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AssignmentTask(db.Model):
    __tablename__ = 'assignment_tasks'
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Shortcut(db.Model):
    __tablename__ = 'shortcuts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    icon = db.Column(db.String(10), default='🔗')

class Note(db.Model):
    __tablename__ = 'notes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(100), nullable=True)
    content = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    links = db.relationship('NoteLink', backref='note', lazy=True, cascade='all, delete-orphan')

class NoteLink(db.Model):
    __tablename__ = 'note_links'
    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(db.Integer, db.ForeignKey('notes.id'), nullable=False)
    label = db.Column(db.String(200), nullable=True)
    url = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)