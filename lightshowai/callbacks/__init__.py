from . import upload_cb, tiled_cb, structure_cb, chatbot_cb, plot_cb, matching_cb, ui_cb

def register_all_callbacks(app):
    upload_cb.register_callbacks(app)
    tiled_cb.register_callbacks(app)
    structure_cb.register_callbacks(app)
    chatbot_cb.register_callbacks(app)
    plot_cb.register_callbacks(app)
    matching_cb.register_callbacks(app)
    ui_cb.register_callbacks(app)
