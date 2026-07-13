import time

from flask import Flask, redirect, send_from_directory


def create_app():
    app = Flask(__name__)
    app.config.from_object('config')

    @app.context_processor
    def inject_cache_bust():
        return {'cache_bust': int(time.time())}

    from tools.guides_routes import guides_bp
    app.register_blueprint(guides_bp)

    @app.route('/robots.txt')
    def robots_txt():
        return send_from_directory(app.static_folder, 'robots.txt')

    @app.route('/sitemap.xml')
    def sitemap_xml():
        return send_from_directory(app.static_folder, 'sitemap.xml',
                                   mimetype='application/xml')

    @app.route('/')
    def index():
        return redirect('/best-weapon-against', code=302)

    @app.errorhandler(404)
    def not_found(e):
        return redirect('/best-weapon-against', code=302)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5003)
