FROM docker.io/library/python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1
WORKDIR /app
COPY coursepilot.py ./
COPY data ./data
COPY tests ./tests
USER 10001:10001
ENTRYPOINT ["python", "/app/coursepilot.py"]
CMD ["plan"]
