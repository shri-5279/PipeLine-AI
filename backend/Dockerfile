# Every Dockerfile starts with FROM — it specifies the BASE IMAGE
# We're starting from an official Python image provided by Docker
# 'python:3.11-slim' means:
#   - Python version 3.11
#   - 'slim' variant = smaller image, only essential OS packages included
#   - Without 'slim' you get a full Debian OS which is 3x larger
# Smaller images = faster deployments, less storage cost
FROM python:3.11-slim

# WORKDIR sets the working directory INSIDE the container
# All subsequent commands run from this directory
# If it doesn't exist, Docker creates it automatically
# Think of this as 'cd /app' but permanent for all future commands
WORKDIR /app

# ENV sets environment variables inside the container
# PYTHONDONTWRITEBYTECODE=1 stops Python from creating .pyc files
#   (we don't need them in containers — they're for repeated execution speedup)
# PYTHONUNBUFFERED=1 forces Python to print output immediately
#   Without this, your logs might not appear in real time
#   Very important for a server — you want to see logs as they happen
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# COPY copies files FROM your local machine INTO the container
# First argument = source path on YOUR machine (relative to Dockerfile location)
# Second argument = destination path INSIDE the container
# We copy requirements.txt FIRST — before copying the rest of the code
# WHY? Docker builds images in layers and caches each layer
# If requirements.txt hasn't changed, Docker reuses the cached pip install layer
# This makes rebuilds much faster — pip install only runs when dependencies change
COPY requirements.txt .

# RUN executes a command during the image BUILD process
# This installs all your Python packages inside the container
# --no-cache-dir tells pip not to save the download cache
#   (saves space — we don't need cached packages in a container)
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of your application code into the container
# The dot '.' means "copy everything from the current directory"
# into the WORKDIR (/app) inside the container
COPY . .

# EXPOSE documents which port this container listens on
# This is documentation only — it doesn't actually open the port
# The actual port binding happens when you run the container
EXPOSE 8000

# CMD is the command that runs when the container STARTS
# This is different from RUN — RUN runs during build, CMD runs at startup
# We're starting uvicorn to serve our FastAPI app
# --host 0.0.0.0 means "listen on all network interfaces"
#   By default uvicorn listens on 127.0.0.1 (localhost only)
#   Inside a container, localhost only = nothing outside can reach it
#   0.0.0.0 = accept connections from anywhere (required for containers)
# --port 8000 = which port to listen on
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]