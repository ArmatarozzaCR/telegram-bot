FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

# LANCIA FLASK SERVER — così si apre la porta 8080 e Fly non crasha
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]