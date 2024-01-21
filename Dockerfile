FROM ubuntu:20.04

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y python3-pip && \
    pip3 install flask APScheduler psycopg2-binary gunicorn joblib requests pytz && \
    rm -rf /var/lib/apt/lists/*

COPY . /opt/app

EXPOSE 8080

WORKDIR /opt/app

CMD ["gunicorn", "-w 4", "-t 86400", "app.main:app", "--bind", "0.0.0.0:8080"]
