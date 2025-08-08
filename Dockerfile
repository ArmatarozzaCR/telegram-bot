FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY main.py main.py
COPY credentials.json credentials.json
# Copia eventuali altri file necessari

CMD ["python3", "main.py"]
