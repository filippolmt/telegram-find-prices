FROM python:3.14-slim

WORKDIR /app

# Installa uv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia i file di progetto e installa le dipendenze
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copia il codice sorgente e i test
COPY src/ src/
COPY tests/ tests/

# Crea utente non-root e directory dati
RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p data \
    && chown -R appuser:appuser /app /home/appuser

USER appuser

CMD ["uv", "run", "python", "src/bot.py"]
