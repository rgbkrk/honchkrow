"""Serve up a notebook session to ChatGPT.

Within your notebook, make this your first cell:

try:
    await server.shutdown()
except NameError:
    pass

import importlib
import ipyserve

importlib.reload(ipyserve)

server = ipyserve.serve_in_jupyter()

"""
import asyncio
import base64
from typing import Dict, List, Optional, Tuple

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from IPython import get_ipython
from IPython.utils.capture import capture_output
from pydantic import BaseModel


class RunCellRequest(BaseModel):
    code: str


class DisplayData(BaseModel):
    data: Optional[dict] = None
    metadata: Optional[dict] = None

    @classmethod
    def from_tuple(cls, formatted: Tuple[dict, dict]):
        return cls(data=formatted[0], metadata=formatted[1])


class ErrorData(BaseModel):
    error: str

    @classmethod
    def from_exception(cls, e: Exception):
        return cls(error=str(e) if str(e) else type(e).__name__)


# In memory image store
image_store: Dict[str, bytes] = {}


def store_images(dd: DisplayData) -> DisplayData:
    """Convert all image/png data to URLs that the frontend can fetch"""

    if dd.data and "image/png" in dd.data:
        image_name = f"image-{len(image_store)}.png"

        image_store[image_name] = base64.b64decode(dd.data["image/png"])
        dd.data["image/png"] = f"http://localhost:8000/images/{image_name}"

    return dd


class RunCellResponse(BaseModel):
    success: bool = False
    execute_result: Optional[DisplayData] = None
    error: Optional[str] = ""
    stdout: Optional[str] = ""
    stderr: Optional[str] = ""
    displays: List[DisplayData] = []

    @classmethod
    def from_result(cls, result, stdout, stderr, displays):
        ip = get_ipython()

        execute_result = DisplayData.from_tuple(ip.display_formatter.format(result))
        displays = [DisplayData(data=d.data, metadata=d.metadata) for d in displays]

        # Convert all image/png data to URLs that the frontend can fetch
        displays = [store_images(d) for d in displays]
        execute_result = store_images(execute_result)

        return cls(
            success=True,
            execute_result=execute_result,
            stdout=stdout,
            stderr=stderr,
            displays=displays,
        )

    @classmethod
    def from_error(cls, error):
        return cls(
            success=False,
            result=None,
            error=f"Error executing code: {error}",
        )


# We have to set the servers to show an HTTP localhost so that ChatGPT doesn't try HTTPS in development
app = FastAPI(servers=[{"url": "http://localhost:8000", "description": "Local server"}])

app.add_middleware(
    CORSMiddleware,
    # A tiny bit of CORS to allow ChatGPT to talk to us
    # No other sites should have CORS access
    allow_origins=["https://chat.openai.com"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.get("/.well-known/ai-plugin.json", include_in_schema=False)
async def get_ai_plugin_json():
    return {
        "schema_version": "v1",
        "name_for_human": "Notebook Session",
        "name_for_model": "notebook_session",
        "description_for_human": "Allow ChatGPT to play with data in your running Jupyter notebook server.",
        "description_for_model": "Plugin for playing with data in a jupyter notebook. You can inspect variables and run code.",
        "auth": {"type": "none"},  # YOLO 😂😭
        "api": {
            "type": "openapi",
            "url": "http://localhost:8000/openapi.json",
            "is_user_authenticated": False,
        },
        "logo_url": "http://localhost:8000/logo.png",
        "contact_email": "rgbkrk@gmail.com",
        "legal_info_url": "https://github.com/rgbkrk/honchkrow/issues",
    }


# Serve the OpenAPI spec at /openapi.json
@app.get("/openapi.json", include_in_schema=False)
async def get_openapi():
    return app.openapi()


@app.get("/images/{image_name}", include_in_schema=False)
async def get_image(image_name: str):
    """Get an image by name from the notebook session."""
    try:
        return Response(image_store[image_name], media_type="image/png")
    except KeyError as ke:
        return ErrorData.from_exception(ke)


# Return a best faith markdown representation of the variable name
@app.get("/api/variable/{variable_name}")
async def get_variable(variable_name: str) -> DisplayData:
    """
    Get a variable by name from the notebook session.

    Args:
        variable_name (str): The name of the variable to get.

    Returns:
        DisplayData: The display data for the variable, using the IPython display formatter.

    """
    try:
        ip = get_ipython()
        value = ip.user_ns[variable_name]
        return DisplayData.from_tuple(ip.display_formatter.format(value))
    except KeyError as ke:
        return ErrorData.from_exception(ke)


@app.post("/api/run_cell")
async def execute(request: RunCellRequest) -> RunCellResponse:
    """
    Execute code in the notebook session.

    Args:
        code (str): The code to execute.

    Returns:
        RunCellResponse: The result of the execution, including stdout, stderr, display data, and the execute result.

    """
    try:
        with capture_output() as captured:
            # Execute the code
            ip = get_ipython()
            result = ip.run_cell(request.code)

        if result.success:
            return RunCellResponse.from_result(
                result.result, captured.stdout, captured.stderr, captured.outputs
            )
        else:
            return RunCellResponse.from_error(result.error_in_exec)

    except Exception as e:
        return RunCellResponse(
            success=False, result="", error=f"Error executing code: {e}"
        )


# Serve the logo file at /logo.png
@app.get("/logo.png", include_in_schema=False)
async def get_logo():
    """
    The plugin logo
    """
    return FileResponse("logo.png")


def serve_in_jupyter():
    config = uvicorn.Config(
        app,
    )
    server = uvicorn.Server(config)
    loop = asyncio.get_event_loop()
    loop.create_task(server.serve())

    return server  # so we can shut it down later
