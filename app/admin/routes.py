from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
import csv
import io

from app.models import (db, User, TimeEntry, AuditLog, Message,
                         Schedule, EditRequest, log_audit, now_utc)

admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash("Access denied: admin only.", "danger")
            return redirect(url_for("employee.dashboard"))
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────────────

@admin_bp.route("/")
@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    employees = User.query.filter_by(role="employee").order_by(User.full_name).all()
    # Employees currently clocked in
    open_entries = (TimeEntry.query
                    .filter(TimeEntry.clock_out.is_(None))
                    .join(User, User.id == TimeEntry.user_id)
                    .filter(User.role == "employee", User.is_active == True)
                    .all())
    overdue = [e for e in open_entries if e.overdue_reminder]
    # Pending edit requests
    pending_requests = (EditRequest.query
                        .filter_by(status="pending")
                        .order_by(EditRequest.created_at.desc())
                        .limit(10).all())
    # Unread messages from employees
    unread_messages = (Message.query
                       .filter_by(recipient_id=current_user.id, is_read=False)
                       .order_by(Message.created_at.desc())
                       .limit(10).all())
    # Recent audit activity
    recent_audit = (AuditLog.query
                    .order_by(AuditLog.created_at.desc())
                    .limit(15).all())
    return render_template(
        "admin/dashboard.html",
        employees=employees,
        open_entries=open_entries,
        overdue=overdue,
        pending_requests=pending_requests,
        unread_messages=unread_messages,
        recent_audit=recent_audit,
    )


# ── User Management ───────────────────────────────────────────────────────

@admin_bp.route("/users")
@admin_required
def user_list():
    users = User.query.order_by(User.full_name).all()
    return render_template("admin/user_list.html", users=users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def user_create():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip() or None
        role = request.form.get("role", "employee")
        password = request.form.get("password", "")
        if not username or not full_name or not password:
            flash("Username, full name, and password are required.", "danger")
            return render_template("admin/user_form.html", user=None)
        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return render_template("admin/user_form.html", user=None)
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("admin/user_form.html", user=None)
        new_user = User(username=username, full_name=full_name, email=email, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush()
        log_audit("user.created", actor=current_user, target_user=new_user,
                  target_type="user", target_id=new_user.id,
                  new_value={"username": username, "role": role, "full_name": full_name},
                  request=request)
        db.session.commit()
        flash(f"User '{full_name}' created successfully.", "success")
        return redirect(url_for("admin.user_list"))
    return render_template("admin/user_form.html", user=None)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        old = {"username": user.username, "full_name": user.full_name,
               "email": user.email, "role": user.role}
        user.full_name = request.form.get("full_name", user.full_name).strip()
        user.email = request.form.get("email", "").strip() or None
        if current_user.id != user.id:  # can't change own role
            user.role = request.form.get("role", user.role)
        new = {"username": user.username, "full_name": user.full_name,
               "email": user.email, "role": user.role}
        log_audit("user.edited", actor=current_user, target_user=user,
                  target_type="user", target_id=user.id,
                  old_value=old, new_value=new, request=request)
        db.session.commit()
        flash("User updated.", "success")
        return redirect(url_for("admin.user_list"))
    return render_template("admin/user_form.html", user=user)


@admin_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
@admin_required
def user_deactivate(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("admin.user_list"))
    user.is_active = False
    log_audit("user.deactivated", actor=current_user, target_user=user,
              target_type="user", target_id=user.id, request=request)
    db.session.commit()
    flash(f"'{user.full_name}' has been deactivated.", "warning")
    return redirect(url_for("admin.user_list"))


@admin_bp.route("/users/<int:user_id>/reactivate", methods=["POST"])
@admin_required
def user_reactivate(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = True
    log_audit("user.reactivated", actor=current_user, target_user=user,
              target_type="user", target_id=user.id, request=request)
    db.session.commit()
    flash(f"'{user.full_name}' has been reactivated.", "success")
    return redirect(url_for("admin.user_list"))


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["GET", "POST"])
@admin_required
def user_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        new_pw = request.form.get("new_password", "")
        if len(new_pw) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("admin/reset_password.html", user=user)
        user.set_password(new_pw)
        log_audit("user.password_reset", actor=current_user, target_user=user,
                  target_type="user", target_id=user.id, request=request)
        db.session.commit()
        flash(f"Password for '{user.full_name}' has been reset.", "success")
        return redirect(url_for("admin.user_list"))
    return render_template("admin/reset_password.html", user=user)


# ── Audit Log View ────────────────────────────────────────────────────────

@admin_bp.route("/audit")
@admin_required
def audit_log():
    page = request.args.get("page", 1, type=int)
    logs = (AuditLog.query
            .order_by(AuditLog.created_at.desc())
            .paginate(page=page, per_page=50))
    return render_template("admin/audit_log.html", logs=logs)


@admin_bp.route("/audit/export")
@admin_required
def audit_export():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "timestamp", "action", "actor", "target_user",
                     "target_type", "target_id", "old_value", "new_value",
                     "reason", "ip_address"])
    for log in logs:
        writer.writerow([
            log.id,
            log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            log.action,
            log.actor.username if log.actor else "",
            log.target_user.username if log.target_user else "",
            log.target_type or "",
            log.target_id or "",
            log.old_value or "",
            log.new_value or "",
            log.reason or "",
            log.ip_address or "",
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=audit_log.csv"}
    )


# ── Edit Request Review ───────────────────────────────────────────────────

@admin_bp.route("/edit-requests")
@admin_required
def edit_requests():
    reqs = (EditRequest.query
            .order_by(EditRequest.created_at.desc())
            .all())
    return render_template("admin/edit_requests.html", requests=reqs)


@admin_bp.route("/edit-requests/<int:req_id>/approve", methods=["POST"])
@admin_required
def approve_edit_request(req_id):
    er = EditRequest.query.get_or_404(req_id)
    if er.status != "pending":
        flash("Request already processed.", "warning")
        return redirect(url_for("admin.edit_requests"))
    entry = er.time_entry
    old = entry.to_dict()
    if er.requested_clock_in:
        entry.clock_in = er.requested_clock_in
    if er.requested_clock_out:
        entry.clock_out = er.requested_clock_out
    if entry.clock_out:
        delta = entry.clock_out - entry.clock_in
        entry.total_minutes = int(delta.total_seconds() / 60)
    entry.status = "edited"
    er.status = "approved"
    er.reviewed_by = current_user.id
    er.reviewed_at = now_utc()
    log_audit("time_entry.edited", actor=current_user,
              target_user=entry.employee, target_type="time_entry",
              target_id=entry.id, old_value=old, new_value=entry.to_dict(),
              reason=f"Approved edit request #{er.id}: {er.reason}",
              request=request)
    db.session.commit()
    flash("Edit request approved and time entry updated.", "success")
    return redirect(url_for("admin.edit_requests"))


@admin_bp.route("/edit-requests/<int:req_id>/deny", methods=["POST"])
@admin_required
def deny_edit_request(req_id):
    er = EditRequest.query.get_or_404(req_id)
    if er.status != "pending":
        flash("Request already processed.", "warning")
        return redirect(url_for("admin.edit_requests"))
    er.status = "denied"
    er.reviewed_by = current_user.id
    er.reviewed_at = now_utc()
    # Reset entry status if it was pending_edit and no other pending requests
    entry = er.time_entry
    other_pending = EditRequest.query.filter_by(
        entry_id=entry.id, status="pending").filter(EditRequest.id != er.id).count()
    if entry.status == "pending_edit" and other_pending == 0:
        entry.status = "normal"
    log_audit("edit_request.denied", actor=current_user,
              target_user=er.requester, target_type="edit_request",
              target_id=er.id, request=request)
    db.session.commit()
    flash("Edit request denied.", "info")
    return redirect(url_for("admin.edit_requests"))


# ── All-employee CSV Export ───────────────────────────────────────────────

@admin_bp.route("/export/time-entries")
@admin_required
def export_time_entries():
    entries = (TimeEntry.query
               .join(User, User.id == TimeEntry.user_id)
               .filter(User.role == "employee")
               .order_by(User.full_name, TimeEntry.clock_in)
               .all())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["employee_name", "username", "date", "clock_in",
                     "clock_out", "total_hours", "status", "notes"])
    for e in entries:
        writer.writerow([
            e.employee.full_name,
            e.employee.username,
            e.clock_in.strftime("%Y-%m-%d") if e.clock_in else "",
            e.clock_in.strftime("%Y-%m-%d %H:%M") if e.clock_in else "",
            e.clock_out.strftime("%Y-%m-%d %H:%M") if e.clock_out else "",
            f"{(e.total_minutes or 0) / 60:.2f}",
            e.status,
            e.notes or "",
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=all_time_entries.csv"}
    )


@admin_bp.route("/export/schedules")
@admin_required
def export_schedules():
    schedules = (Schedule.query
                 .join(User, User.id == Schedule.user_id)
                 .order_by(User.full_name, Schedule.shift_start)
                 .all())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["employee_name", "username", "shift_start", "shift_end", "notes"])
    for s in schedules:
        writer.writerow([
            s.employee_schedule.full_name,
            s.employee_schedule.username,
            s.shift_start.strftime("%Y-%m-%d %H:%M"),
            s.shift_end.strftime("%Y-%m-%d %H:%M"),
            s.notes or "",
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=schedules.csv"}
    )
