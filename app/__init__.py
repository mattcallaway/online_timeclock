from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate

from app.models import db, User
from app.config import config_by_name
import os


login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, template_folder="templates")
    cfg = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(cfg)

    # Extensions
    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)

    # Blueprints
    from app.auth.routes import auth_bp
    from app.admin.routes import admin_bp
    from app.employee.routes import employee_bp
    from app.timeclock.routes import timeclock_bp
    from app.schedule.routes import schedule_bp
    from app.messages.routes import messages_bp
    from app.turf.routes import turf_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(employee_bp, url_prefix="/employee")
    app.register_blueprint(timeclock_bp, url_prefix="/timeclock")
    app.register_blueprint(schedule_bp, url_prefix="/schedule")
    app.register_blueprint(messages_bp, url_prefix="/messages")
    app.register_blueprint(turf_bp, url_prefix="/turf")

    # Root redirect
    from flask import redirect, url_for
    from flask_login import current_user

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("employee.dashboard"))
        return redirect(url_for("auth.login"))

    return app
