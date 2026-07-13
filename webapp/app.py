import time

from flask import Flask, redirect, send_from_directory


def create_app():
    app = Flask(__name__)
    app.config.from_object('config')

    @app.context_processor
    def inject_cache_bust():
        return {'cache_bust': int(time.time())}

    # Hub at / and per-enemy rankings at /<enemy_slug> (guides_bp has no prefix).
    from tools.guides_routes import guides_bp
    app.register_blueprint(guides_bp)

    @app.route('/robots.txt')
    def robots_txt():
        return send_from_directory(app.static_folder, 'robots.txt')

    @app.route('/sitemap.xml')
    def sitemap_xml():
        return send_from_directory(app.static_folder, 'sitemap.xml',
                                   mimetype='application/xml')

    # Legacy paths from when rankings lived at bloodngold.com/best-weapon-against.
    @app.route('/best-weapon-against')
    def legacy_hub():
        return redirect('/', code=301)

    @app.route('/best-weapon-against/<enemy_slug>')
    def legacy_enemy(enemy_slug):
        return redirect('/' + enemy_slug, code=301)

    @app.errorhandler(404)
    def not_found(e):
        return redirect('/', code=302)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5003)
