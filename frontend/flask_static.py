"""Attach built frontend assets to Person 2's Flask app without editing api.py."""
from pathlib import Path
import json
from flask import jsonify, request, send_from_directory
from quant.presentation import portfolio_summary, selection_summary

DIST = Path(__file__).resolve().parent / "dist"

def register_frontend(app, dist=DIST):
    dist = Path(dist).resolve()
    if not (dist / "index.html").is_file():
        raise RuntimeError("Frontend build missing. Run npm run build in frontend/ first.")

    @app.after_request
    def presentation_headers(response):
        if response.status_code == 200 and response.is_json:
            try:
                if request.path.endswith("/portfolio"):
                    summary=portfolio_summary(response.get_json())
                elif request.path.endswith("/selection"):
                    summary=selection_summary(response.get_json())
                else:
                    return response
                response.headers["X-Mandate-Presentation"]=json.dumps(summary,separators=(",",":"),allow_nan=False)
                response.headers.add("Access-Control-Expose-Headers","X-Mandate-Presentation, X-Mandate-Data")
            except (KeyError,TypeError,ValueError):
                # A malformed API response is rejected at the frontend boundary.
                # Never let presentation decoration break the actual API.
                pass
        return response

    def index():
        return send_from_directory(dist, "index.html")

    def asset(path):
        if path == "api" or path.startswith("api/"):
            return jsonify(error="Unknown API endpoint"), 404
        # Assets must exist; never return HTML in place of missing JavaScript.
        if Path(path).suffix:
            return send_from_directory(dist, path)
        return index()

    if not any(rule.rule == "/" for rule in app.url_map.iter_rules()):
        app.add_url_rule("/", "mandate_index", index)
    app.add_url_rule("/<path:path>", "mandate_static", asset)
    return app
