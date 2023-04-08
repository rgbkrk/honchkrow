import asyncio
import uvicorn
import atexit
from jupyter_console.app import ZMQTerminalIPythonApp
from dangermode.app import app
import os

banner = """
🚨 DANGER MODE FOR CHATGPT 🚨
This is a Jupyter console instance that has been preloaded with the dangermode library.

Run to start the ChatGPT Plugin server:

activate_dangermode()
"""


class DangerModeIPython(ZMQTerminalIPythonApp):
    def init_banner(self):
        self.shell.banner = banner
        self.shell.show_banner()

    def initialize(self, argv=None):
        super().initialize(argv)
        self.shell.run_cell(
            "from dangermode.main import activate_dangermode", store_history=False
        )


def activate_dangermode():
    global server
    config = uvicorn.Config(app)
    server = uvicorn.Server(config)
    loop = asyncio.get_event_loop()
    loop.create_task(server.serve())

    atexit.register(lambda: asyncio.run(server.shutdown()))


if __name__ == "__main__":
    DangerModeIPython.launch_instance(cwd=os.getcwd())
