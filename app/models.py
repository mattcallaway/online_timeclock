import json
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="employee")  # 'admin' or 'employee'
    full_name = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc, nullable=False)

    # Relationships
    time_entries = db.relationship("TimeEntry", foreign_keys="TimeEntry.user_id",
                                   backref="employee", lazy="dynamic")
    sent_messages = db.relationship("Message", foreign_keys="Message.sender_id",
                                    backref="sender", lazy="dynamic")
    received_messages = db.relationship("Message", foreign_keys="Message.recipient_id",
                                        backref="recipient", lazy="dynamic")
    schedules = db.relationship("Schedule", foreign_keys="Schedule.user_id",
                                backref="employee_schedule", lazy="dynamic")
    edit_requests = db.relationship("EditRequest", foreign_keys="EditRequest.requester_id",
                                    backref="requester", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def active_entry(self):
        """Return the currently open (clocked-in) time entry, or None."""
        return TimeEntry.query.filter_by(
            user_id=self.id, clock_out=None
        ).order_by(TimeEntry.clock_in.desc()).first()

    def __repr__(self):
        return f"<User {self.username}>"


# ---------------------------------------------------------------------------
# Time Entries
# ---------------------------------------------------------------------------

class TimeEntry(db.Model):
    __tablename__ = "time_entries"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    clock_in = db.Column(db.DateTime, nullable=False)
    clock_out = db.Column(db.DateTime, nullable=True)
    total_minutes = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(30), default="normal", nullable=False)
    # status values: normal, edited, missed_punch, pending_edit
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc, nullable=False)

    # Relationships
    edit_requests = db.relationship("EditRequest", backref="time_entry", lazy="dynamic")

    @property
    def is_open(self):
        return self.clock_out is None

    @property
    def duration_minutes(self):
        if self.clock_out and self.clock_in:
            delta = self.clock_out - self.clock_in
            return int(delta.total_seconds() / 60)
        if self.clock_in:
            delta = now_utc() - self.clock_in
            return int(delta.total_seconds() / 60)
        return 0

    @property
    def hours_display(self):
        mins = self.duration_minutes
        h = mins // 60
        m = mins % 60
        return f"{h}h {m:02d}m"

    @property
    def overdue_reminder(self):
        """True if open and clocked in for more than 6 hours."""
        if not self.is_open:
            return False
        return self.duration_minutes >= 360

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "clock_in": self.clock_in.isoformat() if self.clock_in else None,
            "clock_out": self.clock_out.isoformat() if self.clock_out else None,
            "total_minutes": self.total_minutes,
            "status": self.status,
            "notes": self.notes,
        }

    def __repr__(self):
        return f"<TimeEntry {self.id} user={self.user_id}>"


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(80), nullable=False)
    target_type = db.Column(db.String(80), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    old_value = db.Column(db.Text, nullable=True)   # JSON string
    new_value = db.Column(db.Text, nullable=True)   # JSON string
    reason = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)

    actor = db.relationship("User", foreign_keys=[actor_id], backref="audit_actions")
    target_user = db.relationship("User", foreign_keys=[target_user_id],
                                  backref="audit_targets")

    def __repr__(self):
        return f"<AuditLog {self.action} by actor={self.actor_id}>"


def log_audit(action, actor=None, target_user=None, target_type=None,
              target_id=None, old_value=None, new_value=None,
              reason=None, request=None):
    """Write a row to audit_logs. Call inside any route that mutates data."""
    ip = None
    ua = None
    if request is not None:
        ip = request.remote_addr
        ua = str(request.user_agent)

    entry = AuditLog(
        actor_id=actor.id if actor else None,
        target_user_id=target_user.id if target_user else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        old_value=json.dumps(old_value) if old_value is not None else None,
        new_value=json.dumps(new_value) if new_value is not None else None,
        reason=reason,
        ip_address=ip,
        user_agent=ua,
    )
    db.session.add(entry)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)

    def __repr__(self):
        return f"<Message {self.id} from={self.sender_id} to={self.recipient_id}>"


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

class Schedule(db.Model):
    __tablename__ = "schedules"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    shift_start = db.Column(db.DateTime, nullable=False)
    shift_end = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc, nullable=False)

    creator = db.relationship("User", foreign_keys=[created_by], backref="created_schedules")

    def __repr__(self):
        return f"<Schedule {self.id} user={self.user_id}>"


# ---------------------------------------------------------------------------
# Edit Requests
# ---------------------------------------------------------------------------

class EditRequest(db.Model):
    __tablename__ = "edit_requests"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey("time_entries.id"), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    requested_clock_in = db.Column(db.DateTime, nullable=True)
    requested_clock_out = db.Column(db.DateTime, nullable=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    # status: pending, approved, denied
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)

    reviewer = db.relationship("User", foreign_keys=[reviewed_by], backref="reviewed_requests")

    def __repr__(self):
        return f"<EditRequest {self.id} entry={self.entry_id} status={self.status}>"
