import logging

from app import app
from app import logs
from app import background
from app.utils import Anacron

logging.getLogger().addHandler(logs.get_console_handler())

schedule_cc = Anacron(900, background.schedule_cc, "schedule_cc")
schedule_cc.start()

update_jenkins = Anacron(60, background.update_jenkins, "update_jenkins")
update_jenkins.start()

try:
    app.run(debug=True, host=app.config["LISTEN_HOST"], use_reloader=False,
            threaded=app.config["ENABLE_THREADS"])
finally:
    schedule_cc.stop()
    update_jenkins.stop()
    schedule_cc.join()
    update_jenkins.join()
