FROM python:3.7

WORKDIR /usr/src/app

COPY requirements.txt .
RUN pip install --trusted-host pypi.org --no-cache-dir -r requirements.txt

ENV APP_HOST 0.0.0.0
ENV FLASK_APP dpow.py
ENV FLASK_DEBUG 0

COPY . .

CMD ["gunicorn", "-k", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", "-w", "1", "--bind", "0.0.0.0:5000", "--timeout", "180", "--access-logfile", "-", "dpow:app"]