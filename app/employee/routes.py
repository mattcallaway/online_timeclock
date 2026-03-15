from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.models import (db, User, TimeEntry, AuditLog, Message,
                         Schedule, log_audit)

employee_bp = Blueprint("employee", __name__, template_folder="../templates/employee")


def employee_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        # Both employees and admins can reach generic employee views
        return f(*args, **kwargs)
    return decorated


@employee_bp.route("/")
@employee_bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    active_entry = current_user.active_entry
    recent_entries = (TimeEntry.query
                      .filter_by(user_id=current_user.id)
                      .order_by(TimeEntry.clock_in.desc())
                      .limit(10).all())
    upcoming_shifts = (Schedule.query
                       .filter_by(user_id=current_user.id)
                       .order_by(Schedule.shift_start.asc())
                       .limit(5).all())
    unread_messages = (Message.query
                       .filter_by(recipient_id=current_user.id, is_read=False)
                       .order_by(Message.created_at.desc())
                       .limit(5).all())
    return render_template(
        "employee/dashboard.html",
        active_entry=active_entry,
        recent_entries=recent_entries,
        upcoming_shifts=upcoming_shifts,
        unread_messages=unread_messages,
    )


@employee_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        old = {"full_name": current_user.full_name, "email": current_user.email}
        current_user.full_name = request.form.get("full_name", current_user.full_name).strip()
        current_user.email = request.form.get("email", "").strip() or None
        new = {"full_name": current_user.full_name, "email": current_user.email}
        log_audit("user.profile_updated", actor=current_user, target_user=current_user,
                  target_type="user", target_id=current_user.id,
                  old_value=old, new_value=new, request=request)
        db.session.commit()
        flash("Profile updated.", "success")
    return render_template("employee/profile.html")


@employee_bp.route("/audit")
@login_required
def my_audit():
    """Employee can view audit trail for their own records."""
    page = request.args.get("page", 1, type=int)
    logs = (AuditLog.query
            .filter_by(target_user_id=current_user.id)
            .order_by(AuditLog.created_at.desc())
            .paginate(page=page, per_page=30))
    return render_template("employee/audit.html", logs=logs)
