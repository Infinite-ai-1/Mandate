"""Run the real shared API with the built frontend: python -m frontend.serve."""
from frontend.flask_static import register_frontend

def main():
    try:
        from api import app
    except ImportError as error:
        raise SystemExit("Shared api.py or one of its dependencies is unavailable. For labelled synthetic preview use python -m frontend.dev.stub_api.") from error
    register_frontend(app)
    app.run(host="127.0.0.1", port=5000, debug=False)

if __name__ == "__main__":
    main()
