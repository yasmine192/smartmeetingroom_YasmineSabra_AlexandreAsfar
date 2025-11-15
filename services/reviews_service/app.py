from flask import Flask, jsonify

def create_app():
    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"service": "reviews", "status": "ok"}), 200

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(port=5004, debug=True)
