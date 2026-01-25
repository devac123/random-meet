How to Deploy Video Chat for Free

This guide uses Render.com because it supports Python and WebSockets on its free tier.

Prerequisites

Create a GitHub account.

Create a Render account.

Step 1: Prepare your Files

Ensure your folder contains these 4 files:

video_chat.py (The main code)

requirements.txt (List of libraries)

Procfile (Start command configuration)

DEPLOY_INSTRUCTIONS.md (This file)

Step 2: Push to GitHub

Create a new Public Repository on GitHub.

Upload your files to this repository.

Step 3: Deploy on Render

Go to your Render Dashboard.

Click New + and select Web Service.

Connect your GitHub account and select the repository you just created.

Scroll down to configure the following settings:

Name: (Give your app a name, e.g., my-video-chat)

Region: (Choose the one closest to you)

Branch: main (or master)

Runtime: Python 3

Build Command: pip install -r requirements.txt

Start Command: gunicorn --worker-class eventlet -w 1 video_chat:app

Instance Type: Select Free.

Click Create Web Service.

Step 4: Wait for Build

Render will now download the libraries and set up the server. This usually takes 2-3 minutes.
Once you see "Your service is live" in the logs, click the URL at the top left (e.g., https://my-video-chat.onrender.com).

Troubleshooting

502 Bad Gateway: usually means the Start Command is wrong. Ensure it is exactly gunicorn --worker-class eventlet -w 1 video_chat:app.

WebSocket Errors: Ensure you didn't accidentally use the standard Gunicorn worker type (sync). The --worker-class eventlet part is mandatory.