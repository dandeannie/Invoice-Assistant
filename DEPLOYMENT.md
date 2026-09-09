# Deployment Guide: Render & Railway

This guide outlines how to deploy the **Invoice Assistant** application on **Render** or **Railway** with continuous deployment from your GitHub repository.

---

## Option 1: Deploy on Render (Recommended)

Render offers a generous free tier with automatic Docker-based builds and HTTPS out of the box.

### Method A: 1-Click Blueprint Deploy (Fastest)

1. Sign in to [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** in the top navigation and select **Blueprint**.
3. Connect your GitHub account and select the **`Invoice-Assistant`** repository.
4. Select the branch to deploy: `feature/redesign-dashboard` (or `main` after merging).
5. Render will automatically detect [`render.yaml`](./render.yaml) and configure:
   - **Environment:** Docker
   - **Dockerfile Path:** `./Dockerfile`
   - **Port:** `10000` (Render default)
   - **Health Check Path:** `/_stcore/health`
6. Click **Apply**. Render will build the Docker container and deploy the app at `https://<your-app-name>.onrender.com`.

### Method B: Manual Web Service Setup

If you prefer manual configuration:
1. Click **New +** → **Web Service**.
2. Connect `https://github.com/dandeannie/Invoice-Assistant.git`.
3. Set the following options:
   - **Name:** `invoice-assistant`
   - **Language / Runtime:** `Docker`
   - **Branch:** `feature/redesign-dashboard` (or `main`)
   - **Region:** Any (e.g., Oregon or Frankfurt)
   - **Instance Type:** Free
4. Under **Advanced Settings**:
   - **Health Check Path:** `/_stcore/health`
5. Click **Deploy Web Service**.

---

## Option 2: Deploy on Railway

Railway automatically detects the [`Dockerfile`](./Dockerfile) and [`railway.json`](./railway.json) configuration.

### Steps to Deploy on Railway:

1. Go to [Railway.app](https://railway.app/) and log in with GitHub.
2. Click **New Project** → **Deploy from GitHub repo**.
3. Select **`dandeannie/Invoice-Assistant`**.
4. Choose branch: `feature/redesign-dashboard` (or `main`).
5. Railway will automatically build using the `Dockerfile`.
6. Once deployed, click on the service:
   - Go to the **Settings** tab.
   - Under **Networking**, click **Generate Domain** to get a public URL (e.g. `https://invoice-assistant-production.up.railway.app`).

---

## Environment Variables (Optional)

If you plan to use cloud LLM features (OpenAI or Anthropic) without entering API keys into the UI every session, set these in the Render/Railway dashboard under **Environment Variables**:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | OpenAI API Key for GPT-4o | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API Key for Claude 3.5 Sonnet | `sk-ant-...` |

*(Note: If no API keys are provided, the application runs 100% offline using template extraction and RapidOCR fallback).*

---

## Testing the Container Locally (Optional)

To test the container on your local machine using Docker:

```bash
# Build the Docker image
docker build -t invoice-assistant .

# Run the container on port 8501
docker run -p 8501:8501 invoice-assistant
```

Access the app at: [http://localhost:8501](http://localhost:8501).
