from http.client import HTTPException
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from fastapi import FastAPI
from fastapi.responses import Response
import functools
import io
from pydantic import BaseModel
import yaml


import hupper
import asyncio
import uvicorn

import random


class RunCellRequest(BaseModel):
    code: str


class RunCellResponse(BaseModel):
    success: bool = False
    result: str = ""
    error: str = ""
    stdout: str = ""
    stderr: str = ""
    display_data: list = []


class MarkdownResponse(BaseModel):
    markdown_repr: str


# Define a model for the variable response
class VariableResponse(BaseModel):
    markdown_repr: str


class RandomResponse(BaseModel):
    random_thing: str


def create_app(ip=None):
    if ip is None:
        from IPython import get_ipython

        ip = get_ipython()

    app = FastAPI(
        servers=[{"url": "http://localhost:8000", "description": "Local server"}]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://chat.openai.com"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app.get("/.well-known/ai-plugin.json")
    async def get_ai_plugin_json():
        return {
            "schema_version": "v1",
            "name_for_human": "Notebook Session",
            "name_for_model": "notebook_session",
            "description_for_human": "Allow ChatGPT to play with data in your running Jupyter notebook server.",
            "description_for_model": "Plugin for playing with data in a jupyter notebook. You can inspect variables.",
            "auth": {"type": "none"},
            "api": {
                "type": "openapi",
                "url": "http://localhost:8000/openapi.json",
                "is_user_authenticated": False,
            },
            "logo_url": "http://localhost:8000/logo.png",
            "contact_email": "rgbkrk@gmail.com",
            "legal_info_url": "http://www.example.com/legal",
        }

    # Serve the OpenAPI spec at /openapi.json
    @app.get("/openapi.json")
    async def get_openapi():
        return app.openapi(
            servers=[{"url": "http://localhost:8000", "description": "Local server"}]
        )

    # Return a best faith markdown representation of the variable name
    @app.get("/api/variable/{variable_name}", response_model=VariableResponse)
    async def get_variable(variable_name: str):
        """
        Get a variable by name from the notebook session.

        Args:
            variable_name (str): The name of the variable to get.

        Returns:
            dict: A dictionary with a single key, `markdown_repr`, which is a best faith markdown representation of the variable.
        """
        try:
            value = ip.user_ns[variable_name]
        except KeyError:
            return {"markdown_repr": f"Variable `{variable_name}` not found."}

        return {"markdown_repr": f"{repr(value)}"}

    @app.post("/api/run_cell", response_model=RunCellResponse)
    async def execute(request: RunCellRequest) -> RunCellResponse:
        """
        Execute code in the notebook session.

        Args:
            code (str): The code to execute.

        """
        try:
            from IPython.utils.capture import capture_output

            with capture_output() as captured:
                # Execute the code
                result = ip.run_cell(request.code)

            if result.success:
                output = {
                    "success": True,
                    "result": str(result.result),
                    "stdout": captured.stdout,
                    "stderr": captured.stderr,
                    "display_data": [],
                }
                # Add display data from the captured output
                for display_data in captured.outputs:
                    output["display_data"].append(display_data.to_dict())

                return RunCellResponse(**output)
            else:
                return RunCellResponse(
                    success=False,
                    result="",
                    error=f"Error executing code: {result.error_in_exec}",
                )

        except Exception as e:
            return RunCellResponse(
                success=False, result="", error=f"Error executing code: {e}"
            )

    @app.get("/api/random", response_model=RandomResponse)
    async def get_random():
        """
        Get a random thing from the notebook session.

        Args:
            variable_name (str): The name of the variable to get.

        Returns:
            dict: A dictionary with a single key, `markdown_repr`, which is a best faith markdown representation of the variable.
        """
        return {"random_thing": random.choice(["a", "b", "c"])}

    # Serve the logo file at /logo.png
    @app.get("/logo.png")
    async def get_logo():
        """
        The plugin logo
        """
        return FileResponse("logo.png")

    @app.get("/")
    async def root():
        return {"message": f"All systems are a go"}

    return app


def serve_in_jupyter(app):
    # import nest_asyncio

    # nest_asyncio.apply()

    # import asyncio
    # import uvicorn

    # config = uvicorn.Config(app)
    # server = uvicorn.Server(config)
    # loop = asyncio.get_event_loop()
    # loop.create_task(server.serve())

    # Not sure if we can set reload=True to get automatic reloading when you change your code
    # So instead we have to use hupper

    config = uvicorn.Config(
        app,
        # log_level="debug",
    )
    server = uvicorn.Server(config)
    loop = asyncio.get_event_loop()
    loop.create_task(server.serve())

    return server  # so we can shut it down later


def kill_server(server):
    server.should_exit = True
    server.shutdown()
