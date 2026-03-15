from flask import (Blueprint, render_template, redirect, url_for, flash, request)
from flask_login import login_required, current_user

from app.models import db, User, Message, log_audit

messages_bp = Blueprint("messages", __name__, template_folder="../templates/messages")


def _get_admin():
    """Return the first active admin user."""
    return User.query.filter_by(role="admin", is_active=True).first()


@messages_bp.route("/inbox")
@login_required
def inbox():
    messages = (Message.query
                .filter_by(recipient_id=current_user.id)
                .order_by(Message.created_at.desc())
                .all())
    return render_template("messages/inbox.html", messages=messages)


@messages_bp.route("/sent")
@login_required
def sent():
    messages = (Message.query
                .filter_by(sender_id=current_user.id)
                .order_by(Message.created_at.desc())
                .all())
    return render_template("messages/sent.html", messages=messages)


@messages_bp.route("/<int:msg_id>")
@login_required
def read_message(msg_id):
    msg = Message.query.get_or_404(msg_id)
    # Permission: only sender or recipient can read
    if msg.recipient_id != current_user.id and msg.sender_id != current_user.id:
        flash("Access denied.", "danger")
        return redirect(url_for("messages.inbox"))
    if msg.recipient_id == current_user.id and not msg.is_read:
        msg.is_read = True
        db.session.commit()
    return render_template("messages/read.html", msg=msg)


@messages_bp.route("/compose", methods=["GET", "POST"])
@login_required
def compose():
    # Admin can pick any employee; employees can only message admin
    if current_user.is_admin:
        recipients = User.query.filter_by(role="employee", is_active=True).order_by(User.full_name).all()
        default_recipient_id = request.args.get("to", type=int)
    else:
        admin = _get_admin()
        recipients = [admin] if admin else []
        default_recipient_id = admin.id if admin else None

    if request.method == "POST":
        recipient_id = request.form.get("recipient_id", type=int)
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()

        if not recipient_id or not subject or not body:
            flash("All fields are required.", "danger")
            return render_template("messages/compose.html",
                                   recipients=recipients,
                                   default_recipient_id=default_recipient_id)

        recipient = User.query.get(recipient_id)
        if not recipient:
            flash("Invalid recipient.", "danger")
            return redirect(url_for("messages.compose"))

        # Enforce routing rules
        if not current_user.is_admin:
            # Employees may only message admin
            if recipient.role != "admin":
                flash("You may only send messages to an administrator.", "danger")
                return redirect(url_for("messages.compose"))
        else:
            # Admin may only message employees
            if recipient.role == "admin" and recipient.id != current_user.id:
                flash("Admins can only message employees via this system.", "danger")
                return redirect(url_for("messages.compose"))

        msg = Message(
            sender_id=current_user.id,
            recipient_id=recipient_id,
            subject=subject,
            body=body,
        )
        db.session.add(msg)
        db.session.flush()
        log_audit("message.sent", actor=current_user, target_user=recipient,
                  target_type="message", target_id=msg.id,
                  new_value={"subject": subject}, request=request)
        db.session.commit()
        flash("Message sent.", "success")
        return redirect(url_for("messages.sent"))

    return render_template("messages/compose.html",
                           recipients=recipients,
                           default_recipient_id=default_recipient_id)


@messages_bp.route("/<int:msg_id>/delete", methods=["POST"])
@login_required
def delete_message(msg_id):
    msg = Message.query.get_or_404(msg_id)
    if msg.recipient_id != current_user.id and msg.sender_id != current_user.id:
        flash("Access denied.", "danger")
        return redirect(url_for("messages.inbox"))
    db.session.delete(msg)
    db.session.commit()
    flash("Message deleted.", "info")
    return redirect(url_for("messages.inbox"))
