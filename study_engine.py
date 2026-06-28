import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import json
from datetime import datetime, timezone, timedelta

def generate_training_data():
    """Generate synthetic training data for the study recommendation model."""
    np.random.seed(42)
    n = 500
    
    data = []
    subjects = ['Mathematics', 'English', 'Science', 'History', 'Computing', 'Economics']
    
    for _ in range(n):
        avg_mark = np.random.uniform(20, 100)
        days_until_due = np.random.randint(0, 30)
        weight = np.random.uniform(5, 40)
        num_flashcard_decks = np.random.randint(0, 10)
        cards_studied_recently = np.random.randint(0, 50)
        streak = np.random.randint(0, 30)
        num_assessments = np.random.randint(1, 10)
        
        # Determine priority label based on heuristics
        score = 0
        if avg_mark < 50: score += 3
        elif avg_mark < 70: score += 2
        else: score += 0
        
        if days_until_due < 3: score += 4
        elif days_until_due < 7: score += 2
        elif days_until_due < 14: score += 1
        
        if weight > 25: score += 3
        elif weight > 15: score += 2
        else: score += 1
        
        if streak == 0: score += 2
        if cards_studied_recently < 5: score += 1
        
        if score >= 8: priority = 'critical'
        elif score >= 5: priority = 'high'
        elif score >= 3: priority = 'medium'
        else: priority = 'low'
        
        data.append({
            'avg_mark': avg_mark,
            'days_until_due': days_until_due,
            'weight': weight,
            'num_flashcard_decks': num_flashcard_decks,
            'cards_studied_recently': cards_studied_recently,
            'streak': streak,
            'num_assessments': num_assessments,
            'priority': priority
        })
    
    return pd.DataFrame(data)


def train_model():
    """Train the recommendation model and return it with the encoder."""
    df = generate_training_data()
    
    le = LabelEncoder()
    df['priority_encoded'] = le.fit_transform(df['priority'])
    
    features = ['avg_mark', 'days_until_due', 'weight', 'num_flashcard_decks', 
                'cards_studied_recently', 'streak', 'num_assessments']
    
    X = df[features]
    y = df['priority_encoded']
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    return model, le, features


# Train once at module load
_model, _le, _features = train_model()


def get_study_recommendations(user_marks, user_assignments, user_decks, user_streak):
    """
    Generate personalised study recommendations.
    Returns a list of recommendation dicts sorted by priority.
    """
    recommendations = []
    now = datetime.now(timezone.utc)
    
    # Group marks by subject
    subject_marks = {}
    for m in user_marks:
        if m.active:
            if m.subject not in subject_marks:
                subject_marks[m.subject] = []
            subject_marks[m.subject].append(m)
    
    # Calculate weighted averages per subject
    subject_averages = {}
    for subject, marks in subject_marks.items():
        if marks:
            weighted_sum = sum((m.mark / m.max_mark) * m.weight for m in marks)
            total_weight = sum(m.weight for m in marks)
            subject_averages[subject] = round((weighted_sum / total_weight) * 100, 1) if total_weight else 0
    
    # Find upcoming assignments
    upcoming = [a for a in user_assignments if not a.completed]
    
    # Count decks per subject (rough match)
    deck_subjects = {}
    for deck in user_decks:
        subj = deck.subject.lower()
        deck_subjects[subj] = deck_subjects.get(subj, 0) + 1
    
    # Cards studied recently -approximate from deck count
    cards_per_subject = {}
    for deck in user_decks:
        subj = deck.subject.lower()
        cards_per_subject[subj] = cards_per_subject.get(subj, 0) + len(deck.cards)
    
    processed_subjects = set()
    
    # Recommendations based on assignments
    for assignment in upcoming:
        due = assignment.due_date
        if due is not None:
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            days_until = max(0, (due - now).days)
        else:
            days_until = 14  # no due date set — treat as medium-term, not urgent
        
        subject = assignment.subject
        avg = subject_averages.get(subject, 60.0)
        deck_count = deck_subjects.get(subject.lower(), 0)
        cards_recent = cards_per_subject.get(subject.lower(), 0)
        num_assessments = len(subject_marks.get(subject, []))
        
        features_input = pd.DataFrame([{
            'avg_mark': avg,
            'days_until_due': days_until,
            'weight': 20,
            'num_flashcard_decks': deck_count,
            'cards_studied_recently': min(cards_recent, 50),
            'streak': user_streak or 0,
            'num_assessments': num_assessments
        }])
        
        priority_encoded = _model.predict(features_input)[0]
        priority = _le.inverse_transform([priority_encoded])[0]
        
        tip = _generate_tip(priority, avg, days_until, deck_count, user_streak)
        
        recommendations.append({
            'subject': subject,
            'assignment': assignment.title,
            'due_in_days': days_until,
            'average': avg,
            'priority': priority,
            'tip': tip
        })
        processed_subjects.add(subject)
    
    # Recommendations for subjects without upcoming assignments but low marks
    for subject, avg in subject_averages.items():
        if subject in processed_subjects:
            continue
        if avg < 70:
            deck_count = deck_subjects.get(subject.lower(), 0)
            cards_recent = cards_per_subject.get(subject.lower(), 0)
            num_assessments = len(subject_marks.get(subject, []))
            
            features_input = pd.DataFrame([{
                'avg_mark': avg,
                'days_until_due': 14,
                'weight': 15,
                'num_flashcard_decks': deck_count,
                'cards_studied_recently': min(cards_recent, 50),
                'streak': user_streak or 0,
                'num_assessments': num_assessments
            }])
            
            priority_encoded = _model.predict(features_input)[0]
            priority = _le.inverse_transform([priority_encoded])[0]
            tip = _generate_tip(priority, avg, 14, deck_count, user_streak)
            
            recommendations.append({
                'subject': subject,
                'assignment': None,
                'due_in_days': None,
                'average': avg,
                'priority': priority,
                'tip': tip
            })
    
    # Sort by priority severity
    order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    recommendations.sort(key=lambda x: order.get(x['priority'], 4))
    
    return recommendations[:6]  # Top 6


def _generate_tip(priority, avg, days_until_due, deck_count, streak):
    """Generate a human-readable study tip."""
    tips = {
        'critical': [
            f"Your average is {avg:.0f}% -focus here immediately. Block out dedicated study time today.",
            f"Only {days_until_due} day{'s' if days_until_due != 1 else ''} until your assessment. Prioritise this above everything else.",
            "Create a flashcard deck for this subject right now and drill the key concepts.",
        ],
        'high': [
            f"Average of {avg:.0f}% -room to improve. Aim for consistent daily revision.",
            f"{'Start' if deck_count == 0 else 'Review'} your flashcard decks for this subject.",
            "Break the content into smaller topics and tackle one per study session.",
        ],
        'medium': [
            f"You're tracking at {avg:.0f}% -keep the momentum going with regular review.",
            "Revisit past feedback and identify patterns in your mistakes.",
            "A 20-minute review session today will pay dividends later.",
        ],
        'low': [
            f"Solid {avg:.0f}% average -maintain it with light touch revision.",
            "You're on track. Keep your streak going and stay consistent.",
            "Consider helping a classmate -teaching reinforces your own understanding.",
        ]
    }
    
    if streak == 0 and priority in ('critical', 'high'):
        return "You haven't studied recently. Even 15 minutes today will help rebuild momentum."
    
    import random
    random.seed(int(avg + (days_until_due or 0)))
    tip_list = tips.get(priority, tips['medium'])
    return random.choice(tip_list)