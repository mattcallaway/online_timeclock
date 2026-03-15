from flask import (Blueprint, render_template, redirect, url_for, flash, request)
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from app.models import db, User, Schedule, log_audit

schedule_bp = Blueprint("schedule", __name__, template_folder="../templates/schedule")


def _parse_dt(s):
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None


@schedule_bp.route("/")
@login_required
def view_schedule():
    """Month/week calendar view — all employees see their own shifts; admins see all."""
    # Default: current week
    week_start_str = request.args.get("week")
    if week_start_str:
        try:
            week_start = datetime.strptime(week_start_str, "%Y-%m-%d")
        except ValueError:
            week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    else:
        week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)

    q = Schedule.query.filter(
        Schedule.shift_start >= week_start,
        Schedule.shift_start < week_end,
    )
    if not current_user.is_admin:
        q = q.filter_by(user_id=current_user.id)

    shifts = q.order_by(Schedule.shift_start).all()
    employees = User.query.filter_by(role="employee", is_active=True).order_by(User.full_name).all() if current_user.is_admin else []

    prev_week = (week_start - timedelta(days=7)).strftime("%Y-%m-%d")
    next_week = (week_start + timedelta(days=7)).strftime("%Y-%m-%d")

    return render_template("schedule/view.html",
                           shifts=shifts,
                           week_start=week_start,
                           week_end=week_end,
                           prev_week=prev_week,
                           next_week=next_week,
                           employees=employees)


@schedule_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_shift():
    if not current_user.is_admin:
        flash("Only admins can create shifts.", "danger")
        return redirect(url_for("schedule.view_schedule"))
    employees = User.query.filter_by(role="employee", is_active=True).order_by(User.full_name).all()
    if request.method == "POST":
        user_id = request.form.get("user_id", type=int)
        shift_start = _parse_dt(request.form.get("shift_start", ""))
        shift_end = _parse_dt(request.form.get("shift_end", ""))
        notes = request.form.get("notes", "").strip() or None
        if not user_id or not shift_start or not shift_end:
            flash("Employee, start, and end are required.", "danger")
            return render_template("schedule/shift_form.html", employees=employees, shift=None)
        if shift_end <= shift_start:
            flash("Shift end must be after shift start.", "danger")
            return render_template("schedule/shift_form.html", employees=employees, shift=None)
        shift = Schedule(
            user_id=user_id,
            shift_start=shift_start,
            shift_end=shift_end,
            notes=notes,
            created_by=current_user.id,
        )
        db.session.add(shift)
        db.session.flush()
        target = User.query.get(user_id)
        log_audit("schedule.created", actor=current_user, target_user=target,
                  target_type="schedule", target_id=shift.id,
                  new_value={"shift_start": shift_start.isoformat(), "shift_end": shift_end.isoformat()},
                  request=request)
        db.session.commit()
        flash("Shift created.", "success")
        return redirect(url_for("schedule.view_schedule"))
    return render_template("schedule/shift_form.html", employees=employees, shift=None)


@schedule_bp.route("/<int:shift_id>/edit", methods=["GET", "POST"])
@login_required
def edit_shift(shift_id):
    if not current_user.is_admin:
        flash("Only admins can edit shifts.", "danger")
        return redirect(url_for("schedule.view_schedule"))
    shift = Schedule.query.get_or_404(shift_id)
    employees = User.query.filter_by(role="employee", is_active=True).order_by(User.full_name).all()
    if request.method == "POST":
        old = {"shift_start": shift.shift_start.isoformat(), "shift_end": shift.shift_end.isoformat()}
        shift.user_id = request.form.get("user_id", shift.user_id, type=int)
        shift.shift_start = _parse_dt(request.form.get("shift_start", "")) or shift.shift_start
        shift.shift_end = _parse_dt(request.form.get("shift_end", "")) or shift.shift_end
        shift.notes = request.form.get("notes", "").strip() or None
        log_audit("schedule.updated", actor=current_user,
                  target_user=User.query.get(shift.user_id),
                  target_type="schedule", target_id=shift.id,
                  old_value=old,
                  new_value={"shift_start": shift.shift_start.isoformat(),
                             "shift_end": shift.shift_end.isoformat()},
                  request=request)
        db.session.commit()
        flash("Shift updated.", "success")
        return redirect(url_for("schedule.view_schedule"))
    return render_template("schedule/shift_form.html", employees=employees, shift=shift)


@schedule_bp.route("/<int:shift_id>/delete", methods=["POST"])
@login_required
def delete_shift(shift_id):
    if not current_user.is_admin:
        flash("Access denied.", "danger")
        return redirect(url_for("schedule.view_schedule"))
    shift = Schedule.query.get_or_404(shift_id)
    log_audit("schedule.deleted", actor=current_user,
              target_user=User.query.get(shift.user_id),
              target_type="schedule", target_id=shift.id,
              old_value={"shift_start": shift.shift_start.isoformat(),
                         "shift_end": shift.shift_end.isoformat()},
              request=request)
    db.session.delete(shift)
    db.session.commit()
    flash("Shift deleted.", "info")
    return redirect(url_for("schedule.view_schedule"))
