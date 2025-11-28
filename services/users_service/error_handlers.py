from flask import jsonify
from werkzeug.exceptions import HTTPException

def register_error_handlers(app):

    @app.errorhandler(HTTPException)
    def handle_http_error(e):
        return jsonify({
            "error": e.description,
            "status": e.code,
            "service": app.name
        }), e.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        return jsonify({
            "error": str(e),
            "status": 500,
            "service": app.name
        }), 500
