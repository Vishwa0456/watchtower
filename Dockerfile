
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir .

# Run as a non-root user - a monitoring tool with process-kill / file-delete
# powers should not run as root inside its own container by default.
RUN useradd --create-home watchtower && chown -R watchtower:watchtower /app
USER watchtower

ENTRYPOINT ["watchtower"]
CMD ["run"]
