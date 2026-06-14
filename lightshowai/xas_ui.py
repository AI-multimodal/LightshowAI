import os
import crystal_toolkit.components as ctc
from app import app, server 
from components.layout import get_layout
from callbacks import register_all_callbacks
from core.patches import apply_pymatgen_patch
from services.tiled_client import start_tiled_listener

apply_pymatgen_patch()

app.layout = get_layout()

register_all_callbacks(app)

ctc.register_crystal_toolkit(app=app, layout=app.layout)

start_tiled_listener()

print("running")

def serve():
    if "MP_API_KEY" not in os.environ:
        print("Environment variable MP_API_KEY not found, "
              "please set your materials project API key to "
              "this environment variable before running this app")
        exit()
    app.run(debug=False, port=8443, host='127.0.0.1')

if __name__ == "__main__":
    serve()