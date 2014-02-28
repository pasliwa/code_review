from app import app

app.run(debug=True, host=app.config["LISTEN_HOST"], threaded=app.config["ENABLE_THREADS"])
