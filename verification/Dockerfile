FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==8.3.5 ruff==0.11.13
COPY runner.py /opt/don-codino/runner.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 HOME=/tmp
WORKDIR /workspace
ENTRYPOINT ["python", "-I", "/opt/don-codino/runner.py"]
