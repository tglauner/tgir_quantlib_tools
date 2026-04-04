from tgir_quantlib_tools import create_app


app = create_app()


if __name__ == "__main__":
    host = app.config["LOCAL_DEV_HOST"]
    port = int(app.config["LOCAL_DEV_PORT"])
    debug_enabled = bool(app.config["FLASK_DEBUG"])
    print(f"Open http://{host}:{port}", flush=True)
    app.run(host=host, port=port, debug=debug_enabled, use_reloader=False)
