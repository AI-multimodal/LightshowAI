from dash import html
import crystal_toolkit.components as ctc

struct_component = ctc.StructureMoleculeComponent(id="st_vis",
                                                  show_image_button=False,
                                                  show_export_button=False)

chatbot_structure_iframe = html.Iframe(
    id="chatbot_structure_iframe",
    srcDoc="",
    style={
        "display": "none",
        "width": "100%",
        "height": "680px",
        "border": "1px solid #e5e5e5",
        "borderRadius": "6px",
        "backgroundColor": "#fff",
        "marginTop": "10px",
    },
    sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads",
)

chatbot_structure_hint = html.Div(
    id="chatbot_structure_hint",
    children="",
    style={"fontSize": "11px", "color": "#666", "marginTop": "8px"},
)
