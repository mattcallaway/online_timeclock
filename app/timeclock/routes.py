from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, Response)
from flask_login import login_required, current_user
from datetime import datetime
import csv
import io

from app.models import (db, User, TimeEntry, EditRequest,
                         AuditLog, log_audit, now_utc)

timeclock_bp = Blueprint("timeclock", __name__, template_folder="../templates/timeclock")


def _parse_dt(s):
    """Parse a datetime-local form string to a Python datetime."""
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None


# ── Clock In / Out ─────────────────────────────────────────────────────────

@timeclock_bp.route("/clock-in", methods=["POST"])
@login_required
def clock_in():
    if current_user.active_entry:
        flash("You are already clocked in.", "warning")
        return redirect(url_for("employee.dashboard"))
    entry = TimeEntry(
        user_id=current_user.id,
        clock_in=now_utc(),
        status="normal",
    )
    db.session.add(entry)
    db.session.flush()
    log_audit("time_entry.created", actor=current_user, target_user=current_user,
              target_type="time_entry", target_id=entry.id,
              new_value=entry.to_dict(), request=request)
    db.session.commit()
    flash("You are now clocked in.", "success")
    return redirect(url_for("employee.dashboard"))


@timeclock_bp.route("/clock-out", methods=["POST"])
@login_required
def clock_out():
    entry = current_user.active_entry
    if not entry:
        flash("You are not clocked in.", "warning")
        return redirect(url_for("employee.dashboard"))
    old = entry.to_dict()
    entry.clock_out = now_utc()
    entry.total_minutes = entry.duration_minutes
    log_audit("time_entry.clocked_out", actor=current_user, target_user=current_user,
              target_type="time_entry", target_id=entry.id,
              old_value=old, new_value=entry.to_dict(), request=request)
    db.session.commit()
    flash(f"Clocked out. Shift duration: {entry.hours_display}.", "success")
    return redirect(url_for("employee.dashboard"))


# ── Employee: own entries ──────────────────────────────────────────────────

@timeclock_bp.route("/entries")
@login_required
def my_entries():
    if current_user.is_admin:
        return redirect(url_for("timeclock.all_entries"))
    page = request.args.get("page", 1, type=int)
    entries = (TimeEntry.query
               .filter_by(user_id=current_user.id)
               .order_by(TimeEntry.clock_in.desc())
               .paginate(page=page, per_page=30))
    return render_template("timeclock/my_entries.html", entries=entries)


@timeclock_bp.route("/entries/<int:entry_id>")
@login_required
def entry_detail(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    if not current_user.is_admin and entry.user_id != current_user.id:
        flash("Access denied.", "danger")
        return redirect(url_for("timeclock.my_entries"))
    audit_history = (AuditLog.query
                     .filter_by(target_type="time_entry", target_id=entry_id)
                     .order_by(AuditLog.created_at.desc()).all())
    edit_reqs = (EditRequest.query
                 .filter_by(entry_id=entry_id)
                 .order_by(EditRequest.created_at.desc()).all())
    return render_template("timeclock/entry_detail.html",
                           entry=entry,
                           audit_history=audit_history,
                           edit_reqs=edit_reqs)


# ── Employee: submit edit request ──────────────────────────────────────────

@timeclock_bp.route("/entries/<int:entry_id>/request-edit", methods=["GET", "POST"])
@login_required
def request_edit(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id and not current_user.is_admin:
        flash("Access denied.", "danger")
        return redirect(url_for("timeclock.my_entries"))
    if request.method == "POST":
        req_clock_in = _parse_dt(request.form.get("requested_clock_in", ""))
        req_clock_out = _parse_dt(request.form.get("requested_clock_out", ""))
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("A reason is required.", "danger")
            return render_template("timeclock/edit_request_form.html", entry=entry)
        er = EditRequest(
            entry_id=entry.id,
            requester_id=current_user.id,
            requested_clock_in=req_clock_in,
            requested_clock_out=req_clock_out,
            reason=reason,
        )
        db.session.add(er)
        entry.status = "pending_edit"
        log_audit("edit_request.submitted", actor=current_user, target_user=entry.employee,
                  target_type="edit_request", target_id=entry.id,
                  reason=reason, request=request)
        db.session.commit()
        flash("Edit request submitted. An admin will review it.", "info")
        return redirect(url_for("timeclock.entry_detail", entry_id=entry_id))
    return render_template("timeclock/edit_request_form.html", entry=entry)


# ── Admin: all entries ─────────────────────────────────────────────────────

@timeclock_bp.route("/admin/entries")
@login_required
def all_entries():
    if not current_user.is_admin:
        flash("Access denied.", "danger")
        return redirect(url_for("employee.dashboard"))
    page = request.args.get("page", 1, type=int)
    user_filter = request.args.get("user_id", type=int)
    q = TimeEntry.query
    if user_filter:
        q = q.filter_by(user_id=user_filter)
    entries = q.order_by(TimeEntry.clock_in.desc()).paginate(page=page, per_page=50)
    employees = User.query.filter_by(role="employee").order_by(User.full_name).all()
    return render_template("timeclock/all_entries.html",
                           entries=entries,
                           employees=employees,
                           user_filter=user_filter)


# ── Admin: manual add ──────────────────────────────────────────────────────

@timeclock_bp.route("/admin/entries/new", methods=["GET", "POST"])
@login_required
def admin_add_entry():
    if not current_user.is_admin:
        flash("Access denied.", "danger")
        return redirect(url_for("employee.dashboard"))
    employees = User.query.filter_by(role="employee", is_active=True).order_by(User.full_name).all()
    if request.method == "POST":
        user_id = request.form.get("user_id", type=int)
        clock_in_dt = _parse_dt(request.form.get("clock_in", ""))
        clock_out_dt = _parse_dt(request.form.get("clock_out", ""))
        status = request.form.get("status", "normal")
        notes = request.form.get("notes", "").strip() or None
        reason = request.form.get("reason", "").strip()
        if not user_id or not clock_in_dt:
            flash("Employee and clock-in time are required.", "danger")
            return render_template("timeclock/admin_entry_form.html",
                                   employees=employees, entry=None)
        total_mins = None
        if clock_out_dt:
            total_mins = int((clock_out_dt - clock_in_dt).total_seconds() / 60)
        target_user = User.query.get(user_id)
        entry = TimeEntry(
            user_id=user_id,
            clock_in=clock_in_dt,
            clock_out=clock_out_dt,
            total_minutes=total_mins,
            status=status,
            notes=notes,
        )
        db.session.add(entry)
        db.session.flush()
        log_audit("time_entry.admin_added", actor=current_user,
                  target_user=target_user, target_type="time_entry",
                  target_id=entry.id, new_value=entry.to_dict(),
                  reason=reason, request=request)
        db.session.commit()
        flash("Time entry added.", "success")
        return redirect(url_for("timeclock.all_entries"))
    return render_template("timeclock/admin_entry_form.html",
                           employees=employees, entry=None)


# ── Admin: edit entry ──────────────────────────────────────────────────────

@timeclock_bp.route("/admin/entries/<int:entry_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_entry(entry_id):
    if not current_user.is_admin:
        flash("Access denied.", "danger")
        return redirect(url_for("employee.dashboard"))
    entry = TimeEntry.query.get_or_404(entry_id)
    employees = User.query.filter_by(role="employee", is_active=True).order_by(User.full_name).all()
    if request.method == "POST":
        old = entry.to_dict()
        clock_in_dt = _parse_dt(request.form.get("clock_in", ""))
        clock_out_dt = _parse_dt(request.form.get("clock_out", ""))
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("A reason for the edit is required.", "danger")
            return render_template("timeclock/admin_entry_form.html",
                                   employees=employees, entry=entry)
        if clock_in_dt:
            entry.clock_in = clock_in_dt
        if clock_out_dt:
            entry.clock_out = clock_out_dt
            if entry.clock_in:
                entry.total_minutes = int((entry.clock_out - entry.clock_in).total_seconds() / 60)
        entry.status = request.form.get("status", entry.status)
        entry.notes = request.form.get("notes", "").strip() or entry.notes
        log_audit("time_entry.edited", actor=current_user,
                  target_user=entry.employee, target_type="time_entry",
                  target_id=entry.id, old_value=old, new_value=entry.to_dict(),
                  reason=reason, request=request)
        db.session.commit()
        flash("Time entry updated.", "success")
        return redirect(url_for("timeclock.entry_detail", entry_id=entry.id))
    return render_template("timeclock/admin_entry_form.html",
                           employees=employees, entry=entry)


# ── CSV Export ─────────────────────────────────────────────────────────────

@timeclock_bp.route("/export")
@login_required
def export_own():
    user_id = current_user.id if not current_user.is_admin else request.args.get("user_id", current_user.id, type=int)
    entries = (TimeEntry.query
               .filter_by(user_id=user_id)
               .order_by(TimeEntry.clock_in)
               .all())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "date", "clock_in", "clock_out", "total_hours", "status", "notes"])
    for e in entries:
        writer.writerow([
            e.employee.full_name,
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
        headers={"Content-Disposition": "attachment;filename=my_time_entries.csv"}
    )
