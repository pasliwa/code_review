import logging

from app import app
from app import logs

logging.getLogger().addHandler(logs.get_console_handler())
app.run(debug=True, host=app.config["LISTEN_HOST"], threaded=app.config["ENABLE_THREADS"])
