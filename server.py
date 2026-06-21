from agent.root_agent import db_manager_app
from google.adk.apps.web import WebApp

# This is the "hook" the web UI needs
app = WebApp(db_manager_app)

if __name__ == "__main__":
    app.run()