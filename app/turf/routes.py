from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.models import db, TurfCode, log_audit, now_utc
from app.admin.routes import admin_required

turf_bp = Blueprint("turf", __name__, template_folder="../templates/turf")

# ── Shared Dashboard ──────────────────────────────────────────────────────

@turf_bp.route("/")
@login_required
def index():
    if current_user.is_admin:
        # Admin View
        city_filter = request.args.get("city", "").strip()
        status_filter = request.args.get("status", "").strip()
        
        query = TurfCode.query
        if city_filter:
            query = query.filter(TurfCode.city.ilike(f"%{city_filter}%"))
        if status_filter:
            query = query.filter(TurfCode.status == status_filter)
            
        codes = query.order_by(TurfCode.city, TurfCode.code).all()
        return render_template("turf/index.html", codes=codes, city_filter=city_filter, status_filter=status_filter)
    else:
        # Employee View
        city_filter = request.args.get("city", "").strip()
        
        # Get user's active code
        active_code = TurfCode.query.filter_by(claimed_by_user_id=current_user.id, active_for_user=True).first()
        
        # Get available codes
        query = TurfCode.query.filter_by(status="available")
        if city_filter:
            query = query.filter(TurfCode.city.ilike(f"%{city_filter}%"))
            
        available_codes = query.order_by(TurfCode.city, TurfCode.code).all()
        
        # Group by city for display
        grouped_codes = {}
        for tc in available_codes:
            grouped_codes.setdefault(tc.city, []).append(tc)
            
        return render_template("turf/index.html", active_code=active_code, grouped_codes=grouped_codes, city_filter=city_filter)

# ── Employee Claim ────────────────────────────────────────────────────────

@turf_bp.route("/<int:code_id>/claim", methods=["POST"])
@login_required
def claim_code(code_id):
    if current_user.is_admin:
        flash("Admins cannot claim turf codes.", "danger")
        return redirect(url_for("turf.index"))
        
    code = TurfCode.query.get_or_404(code_id)
    if code.status != "available":
        flash("This code is no longer available.", "warning")
        return redirect(url_for("turf.index"))
        
    # Deactivate current active code for user
    prev_active = TurfCode.query.filter_by(claimed_by_user_id=current_user.id, active_for_user=True).all()
    for pc in prev_active:
        pc.active_for_user = False
        pc.status = "inactive"
        
    # Claim new code
    code.status = "claimed"
    code.claimed_by_user_id = current_user.id
    code.claimed_at = now_utc()
    code.active_for_user = True
    
    log_audit("turf_code.claimed", actor=current_user, target_type="turf_code", target_id=code.id,
              new_value={"code": code.code, "city": code.city}, request=request)
              
    db.session.commit()
    flash(f"Successfully claimed code: {code.code}", "success")
    return redirect(url_for("turf.index"))

@turf_bp.route("/my-codes")
@login_required
def my_codes():
    if current_user.is_admin:
        flash("Admins do not have claimed codes.", "danger")
        return redirect(url_for("turf.index"))
        
    codes = TurfCode.query.filter_by(claimed_by_user_id=current_user.id).order_by(TurfCode.claimed_at.desc()).all()
    return render_template("turf/my_codes.html", codes=codes)

# ── Admin CRUD ────────────────────────────────────────────────────────────

@turf_bp.route("/admin/new", methods=["GET", "POST"])
@admin_required
def new_code():
    if request.method == "POST":
        city = request.form.get("city", "").strip()
        code = request.form.get("code", "").strip()
        description = request.form.get("description", "").strip() or None
        
        if not city or not code:
            flash("City and Code are required.", "danger")
            return render_template("turf/admin_form.html", turf_code=None)
            
        new_tc = TurfCode(city=city, code=code, description=description, created_by_user_id=current_user.id)
        db.session.add(new_tc)
        db.session.flush()
        
        log_audit("turf_code.created", actor=current_user, target_type="turf_code", target_id=new_tc.id,
                  new_value={"city": city, "code": code, "description": description}, request=request)
        db.session.commit()
        
        flash("Turf code created.", "success")
        return redirect(url_for("turf.index"))
        
    return render_template("turf/admin_form.html", turf_code=None)

@turf_bp.route("/admin/<int:code_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_code(code_id):
    tc = TurfCode.query.get_or_404(code_id)
    if request.method == "POST":
        old_val = {"city": tc.city, "code": tc.code, "description": tc.description, "status": tc.status}
        tc.city = request.form.get("city", tc.city).strip()
        tc.code = request.form.get("code", tc.code).strip()
        tc.description = request.form.get("description", "").strip() or None
        # We don't typically allow free-form status edits, but if needed, we could add it.
        
        new_val = {"city": tc.city, "code": tc.code, "description": tc.description, "status": tc.status}
        
        log_audit("turf_code.edited", actor=current_user, target_type="turf_code", target_id=tc.id,
                  old_value=old_val, new_value=new_val, request=request)
        db.session.commit()
        
        flash("Turf code updated.", "success")
        return redirect(url_for("turf.index"))
        
    return render_template("turf/admin_form.html", turf_code=tc)

@turf_bp.route("/admin/<int:code_id>/disable", methods=["POST"])
@admin_required
def disable_code(code_id):
    tc = TurfCode.query.get_or_404(code_id)
    tc.status = "disabled"
    if tc.active_for_user:
        tc.active_for_user = False
        
    log_audit("turf_code.disabled", actor=current_user, target_type="turf_code", target_id=tc.id, request=request)
    db.session.commit()
    flash("Turf code disabled.", "warning")
    return redirect(url_for("turf.index"))

@turf_bp.route("/admin/<int:code_id>/reactivate", methods=["POST"])
@admin_required
def reactivate_code(code_id):
    tc = TurfCode.query.get_or_404(code_id)
    # When reactivated, it usually goes back to available, clearing any claimed status
    tc.status = "available"
    tc.claimed_by_user_id = None
    tc.claimed_at = None
    tc.active_for_user = False
    
    log_audit("turf_code.reactivated", actor=current_user, target_type="turf_code", target_id=tc.id, request=request)
    db.session.commit()
    flash("Turf code reactivated and is now available.", "success")
    return redirect(url_for("turf.index"))
