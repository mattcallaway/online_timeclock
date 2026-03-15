"""
Database initialization and admin seed script.
Usage: python init_db.py

Run this ONCE after setting up your environment to create
all tables and the initial admin account.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import db, User

app = create_app(os.environ.get("FLASK_ENV", "development"))


def main():
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Tables created.")

        # Check if admin already exists
        admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        existing = User.query.filter_by(username=admin_username).first()
        if existing:
            print(f"Admin user '{admin_username}' already exists. Skipping seed.")
            return

        admin_password = os.environ.get("ADMIN_PASSWORD")
        if not admin_password:
            print("ERROR: ADMIN_PASSWORD environment variable is required.")
            print("Set it in your .env file or environment before running this script.")
            sys.exit(1)

        admin_full_name = os.environ.get("ADMIN_FULL_NAME", "System Administrator")
        admin_email = os.environ.get("ADMIN_EMAIL", None)

        admin = User(
            username=admin_username,
            full_name=admin_full_name,
            email=admin_email,
            role="admin",
            is_active=True,
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()

        print(f"Admin user '{admin_username}' created successfully.")
        print(f"  Full name: {admin_full_name}")
        print(f"  Login at: http://localhost:5000/login")
        print()
        print("IMPORTANT: Change the admin password after first login!")


if __name__ == "__main__":
    main()
