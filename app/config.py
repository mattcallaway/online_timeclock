import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    REMEMBER_COOKIE_DURATION_DAYS = 30
    REMEMBER_COOKIE_SECURE = False  # Set True behind HTTPS in production
    REMEMBER_COOKIE_HTTPONLY = True


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///timeclock.db"
    )


class ProductionConfig(Config):
    DEBUG = False
    REMEMBER_COOKIE_SECURE = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    @classmethod
    def validate(cls):
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError("SECRET_KEY environment variable must be set in production")
        if not cls.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("DATABASE_URL environment variable must be set in production")


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
