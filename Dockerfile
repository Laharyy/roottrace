# Use a slim, official Python base image -- smaller image size, faster builds,
# and no unnecessary OS packages that could carry vulnerabilities.
FROM python:3.12-slim

WORKDIR /app

# Copy only dependency files first. Docker caches layers -- if requirements.txt
# hasn't changed, this layer is reused on rebuilds instead of reinstalling
# everything from scratch every time you change your actual code.
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual source code.
COPY src/ ./src/
COPY mock_data/ ./mock_data/

# Install our own package (editable install works fine inside a container too).
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "roottrace.api:app", "--host", "0.0.0.0", "--port", "8000"]