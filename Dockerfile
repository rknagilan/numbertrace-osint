# Optional container. Not required for normal use (Kali users can use the venv installer).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt requirements-web.txt ./
RUN pip install -r requirements-web.txt
COPY pyproject.toml README.md LICENSE ./
COPY numbertrace ./numbertrace
RUN pip install --no-deps . && useradd --create-home --uid 10001 app
USER app
EXPOSE 8765
# Inside a container we must bind 0.0.0.0; publish ONLY to localhost on the host:
#   docker run --rm -p 127.0.0.1:8765:8765 numbertrace
CMD ["numbertrace", "serve", "--host", "0.0.0.0", "--allow-remote", "--port", "8765"]
