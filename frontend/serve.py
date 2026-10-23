"""Serve React + Flask: python -m frontend.serve."""
from api import app

def main():
    from waitress import serve
    serve(app, host="127.0.0.1", port=5000, threads=8)

if __name__ == "__main__":
    main()
