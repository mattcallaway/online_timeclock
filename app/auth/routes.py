from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User, log_audit

auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash("Your account has been deactivated. Please contact your administrator.", "danger")
                return render_template("auth/login.html")
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        flash("Invalid username or password.", "danger")
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        
        if not username or not full_name or not password:
            flash("All fields are required.", "danger")
            return render_template("auth/register.html")
            
        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return render_template("auth/register.html")
            
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("auth/register.html")
            
        new_user = User(username=username, full_name=full_name, role="employee")
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        log_audit("user.registered", actor=new_user, target_user=new_user, target_type="user", target_id=new_user.id, request=request)
        db.session.commit()
        
        login_user(new_user, remember=True)
        flash("Account created successfully. Welcome!", "success")
        return redirect(url_for("index"))
        
    return render_template("auth/register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")
        if not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "danger")
        elif len(new_pw) < 8:
            flash("New password must be at least 8 characters.", "danger")
        elif new_pw != confirm_pw:
            flash("Passwords do not match.", "danger")
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            log_audit(
                "user.password_changed",
                actor=current_user,
                target_user=current_user,
                target_type="user",
                target_id=current_user.id,
                request=request,
            )
            db.session.commit()
            flash("Password updated successfully.", "success")
            return redirect(url_for("index"))
    return render_template("auth/change_password.html")
